"""Does the invoiced address exist as a real business?

Google Maps answers in two hops: a search finds the listing, and only a lookup
by place_id carries the website, the phone and the opening state. The second
hop is opt-in because it costs a second credit.

The language comes from the invoiced address through serpapi_locale, because a
Denver listing read in Spanish is the wrong listing read twice. Only hl is sent:
whether engine=google_maps honours gl and google_domain was never confirmed
against a live response, and an unverified parameter on a paid call is a guess
that costs a credit. The address text carries the country in the query itself.
"""

from typing import Any

from autocurricula.tools.base import ToolResult

from countersign.tools import serpapi_parsers as parse
from countersign.tools.serpapi_client import SEARCH_PATH, serpapi_get
from countersign.tools.serpapi_locale import FALLBACK_LOCALE
from countersign.tools.serpapi_models import AddressEvidence
from countersign.tools.serpapi_search import quoted_entity

DEFAULT_MAPS_ZOOM = 16
MIN_MAPS_ZOOM = 3
MAX_MAPS_ZOOM = 30
MAX_PLACES = 10


async def serpapi_verify_address(
    legal_name: str,
    address: str,
    language: str = FALLBACK_LOCALE.language,
    latitude: float | None = None,
    longitude: float | None = None,
    zoom: int = DEFAULT_MAPS_ZOOM,
    fetch_place_details: bool = False,
) -> ToolResult:
    """Check that the invoiced address exists as a real business on Google Maps.

    Mutates no external state; spends one SerpApi credit, or two when
    fetch_place_details makes the lookup that carries the website.
    """
    query = ", ".join(part for part in (quoted_entity(legal_name), address.strip()) if part)
    if not query:
        return ToolResult.failure("legal_name and address are both empty; nothing to look up")
    if (latitude is None) != (longitude is None):
        return ToolResult.failure("latitude and longitude must be given together or not at all")
    if not MIN_MAPS_ZOOM <= zoom <= MAX_MAPS_ZOOM:
        return ToolResult.failure(
            f"zoom {zoom} is outside the google_maps range {MIN_MAPS_ZOOM}..{MAX_MAPS_ZOOM}"
        )
    params: dict[str, Any] = {
        "engine": "google_maps",
        "type": "search",
        "q": query,
        "hl": language,
    }
    if latitude is not None and longitude is not None:
        params["ll"] = f"@{latitude},{longitude},{zoom}z"
    result = await serpapi_get(SEARCH_PATH, params)
    if not result.ok:
        return result
    document = result.payload["document"]
    evidence = AddressEvidence(
        query=query,
        search_id=parse.search_id(document),
        places=parse.places(document, MAX_PLACES),
    )
    if fetch_place_details:
        evidence = await _with_place_details(evidence, language)
    return ToolResult.success(evidence.model_dump(mode="json"))


async def _with_place_details(evidence: AddressEvidence, language: str) -> AddressEvidence:
    """Second hop by place_id. A failure here degrades the evidence, never voids it."""
    if not evidence.places or evidence.places[0].maps_place_id is None:
        return evidence.model_copy(update={"details_error": "no place_id in the maps results"})
    detail = await serpapi_get(
        SEARCH_PATH,
        {
            "engine": "google_maps",
            "place_id": evidence.places[0].maps_place_id,
            "hl": language,
        },
    )
    if not detail.ok:
        return evidence.model_copy(update={"details_error": detail.error})
    record = parse.place_details(detail.payload["document"])
    if record is None:
        return evidence.model_copy(update={"details_error": "no place_results in the response"})
    merged = [parse.merge_place(evidence.places[0], record), *evidence.places[1:]]
    return evidence.model_copy(update={"places": merged, "details_fetched": True})
