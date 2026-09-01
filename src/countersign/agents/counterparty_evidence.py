"""The three searches a counterparty is worth, and not one more.

Two hundred and fifty credits a month, three per counterparty: about eighty
checks before the plan runs dry. So the budget is a constant, the searches run
once and concurrently, and the Maps place-details hop stays off because it would
quietly make the check cost four.

The backend is a protocol so a test can answer with a captured response instead
of spending a credit to prove that parsing works.

The market those three searches run in travels with them. It is derived from the
invoiced address rather than fixed, because a SERP taken in the wrong market is
not weaker evidence about the counterparty, it is evidence about someone else.
"""

import asyncio
from typing import Protocol

from autocurricula.schemas.common import StrictBaseModel
from autocurricula.tools.base import ToolResult
from pydantic import Field

from countersign.agents.capability_gate import gate
from countersign.fleet.roster import COUNTERPARTY_VERIFIER_ID, grants
from countersign.tools.serpapi_address import serpapi_verify_address
from countersign.tools.serpapi_locale import SearchLocale
from countersign.tools.serpapi_models import (
    AddressEvidence,
    AdverseMediaEvidence,
    OfficialSiteEvidence,
)
from countersign.tools.serpapi_search import serpapi_adverse_media, serpapi_find_official_site

SEARCH_BUDGET = 3
ARCHIVE_URL = "https://serpapi.com/searches/{search_id}.json"
SEARCH_TOOLS = (
    "serpapi_find_official_site",
    "serpapi_adverse_media",
    "serpapi_verify_address",
)


def search_denials(agent_id: str = COUNTERPARTY_VERIFIER_ID) -> list[str]:
    """Ask the gate before spending a credit, not after.

    The verifier holds web.search today, so this passes; it is here so that a
    roster change revokes the searches instead of silently leaving them running.
    """
    held = grants().get(agent_id, frozenset())
    refusals = (gate(agent_id, tool, held) for tool in SEARCH_TOOLS)
    return [refusal.reason for refusal in refusals if refusal is not None]


class CounterpartySearches(Protocol):
    """The read-only half of SerpApi, narrowed to what a counterparty needs."""

    async def find_official_site(
        self, *, legal_name: str, locale: SearchLocale
    ) -> ToolResult: ...

    async def adverse_media(
        self, *, legal_name: str, locale: SearchLocale, when_window: str
    ) -> ToolResult: ...

    async def verify_address(
        self, *, legal_name: str, address: str, locale: SearchLocale
    ) -> ToolResult: ...


class SerpApiSearches:
    """The live backend. One credit each, and the second Maps hop never fires."""

    async def find_official_site(self, *, legal_name: str, locale: SearchLocale) -> ToolResult:
        return await serpapi_find_official_site(
            legal_name=legal_name,
            country_code=locale.country_code,
            language=locale.language,
            google_domain=locale.google_domain,
        )

    async def adverse_media(
        self, *, legal_name: str, locale: SearchLocale, when_window: str
    ) -> ToolResult:
        return await serpapi_adverse_media(
            legal_name=legal_name,
            country_code=locale.country_code,
            language=locale.language,
            when_window=when_window,
        )

    async def verify_address(
        self, *, legal_name: str, address: str, locale: SearchLocale
    ) -> ToolResult:
        return await serpapi_verify_address(
            legal_name=legal_name,
            address=address,
            language=locale.language,
            fetch_place_details=False,
        )


class CounterpartyEvidence(StrictBaseModel):
    """What came back, with the failures kept rather than swallowed."""

    official_site: OfficialSiteEvidence | None = None
    adverse_media: AdverseMediaEvidence | None = None
    address: AddressEvidence | None = None
    searches_spent: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def anything_retrieved(self) -> bool:
        return any((self.official_site, self.adverse_media, self.address))


def archive_locator(search_id: str | None, query: str) -> str:
    """The SERP itself, cited when a conclusion rests on the absence of results.

    A negative finding has no result URL to point at, so it points at the search
    that produced nothing instead.
    """
    if search_id:
        return ARCHIVE_URL.format(search_id=search_id)
    return f"serpapi query: {query}" if query.strip() else "serpapi query: (empty)"


async def gather_evidence(
    legal_name: str,
    address: str,
    searches: CounterpartySearches,
    *,
    locale: SearchLocale,
    when_window: str,
) -> CounterpartyEvidence:
    """Spend the budget once, concurrently, and record what each hop cost."""
    address_query = address.strip()
    results = await asyncio.gather(
        searches.find_official_site(legal_name=legal_name, locale=locale),
        searches.adverse_media(
            legal_name=legal_name, locale=locale, when_window=when_window
        ),
        _address_or_skip(searches, legal_name, address_query, locale),
        return_exceptions=True,
    )
    evidence = CounterpartyEvidence(searches_spent=SEARCH_BUDGET if address_query else 2)
    if not address_query:
        evidence.errors.append("no address on the invoice, so the maps search was skipped")
    _absorb(evidence, "official site", results[0], OfficialSiteEvidence)
    _absorb(evidence, "adverse media", results[1], AdverseMediaEvidence)
    if address_query:
        _absorb(evidence, "address", results[2], AddressEvidence)
    return evidence


async def _address_or_skip(
    searches: CounterpartySearches, legal_name: str, address: str, locale: SearchLocale
) -> ToolResult:
    if not address:
        return ToolResult.failure("no address to verify")
    return await searches.verify_address(
        legal_name=legal_name, address=address, locale=locale
    )


def _absorb(
    evidence: CounterpartyEvidence,
    label: str,
    result: ToolResult | BaseException,
    model: type[OfficialSiteEvidence] | type[AdverseMediaEvidence] | type[AddressEvidence],
) -> None:
    """Fold one search into the evidence. A failed hop degrades it, never voids it."""
    if isinstance(result, BaseException):
        evidence.errors.append(f"{label} search raised {type(result).__name__}: {result}")
        return
    if not result.ok:
        evidence.errors.append(f"{label} search failed: {result.error}")
        return
    try:
        parsed = model.model_validate(result.payload)
    except ValueError as error:
        evidence.errors.append(f"{label} response did not match its schema: {error}")
        return
    setattr(evidence, _FIELD[label], parsed)


_FIELD = {
    "official site": "official_site",
    "adverse media": "adverse_media",
    "address": "address",
}
