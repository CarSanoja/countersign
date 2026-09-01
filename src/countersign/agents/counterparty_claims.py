"""Judgement plus evidence becomes a claim, and only then a signal.

Every locator here is read out of the search response, never out of the model's
answer. The model chooses an index; this module turns that index into the URL
that was actually fetched. A judgement pointing at a result that does not exist
is dropped with an error rather than cited to a plausible-looking address.

This file holds the shared citation machinery and the identity finding. Adverse
media lives in counterparty_adverse and the address in counterparty_address.
"""

from urllib.parse import urlparse

from countersign.agents.counterparty_evidence import CounterpartyEvidence, archive_locator
from countersign.agents.counterparty_judgement import CounterpartyJudgement
from countersign.schemas.evidence import Claim, Provider, SourceRef
from countersign.schemas.verdict import RiskSignal, SignalKind
from countersign.tools.serpapi_models import OfficialSiteEvidence

MAX_SNIPPET_CHARS = 300
MIN_SIGNAL_WEIGHT = 0.05
ENTITY_NOT_FOUND_WEIGHT = 0.6
NO_JUDGEMENT_CONFIDENCE = 0.5


def source_ref(locator: str, snippet: str, retrieved_at: str) -> SourceRef:
    return SourceRef(
        provider=Provider.SERPAPI,
        locator=locator,
        snippet=snippet[:MAX_SNIPPET_CHARS],
        retrieved_at=retrieved_at,
    )


def signal_weight(base: float, confidence: float) -> float:
    """Scale a signal by how sure the model was, without letting it reach zero."""
    return max(MIN_SIGNAL_WEIGHT, min(1.0, base * confidence))


def domain_of(locator: str) -> str | None:
    """The host of a fetched URL, or nothing when the locator was not a URL."""
    parsed = urlparse(locator if "//" in locator else f"//{locator}", scheme="https")
    host = (parsed.netloc or "").split("@")[-1].split(":")[0].strip().lower()
    host = host.removeprefix("www.")
    return host if "." in host else None


def official_site_findings(
    legal_name: str, judgement: CounterpartyJudgement, evidence: CounterpartyEvidence, at: str
) -> tuple[list[Claim], list[RiskSignal], str | None, list[str]]:
    """The entity's own domain, or an evidenced statement that none was found."""
    site = evidence.official_site
    if site is None:
        return [], [], None, []
    fallback = archive_locator(site.search_id, site.query)
    call = judgement.official_site
    if call is None or not call.same_entity:
        return _not_found(legal_name, judgement, site, fallback, at)
    locator, snippet, error = _resolve_site(call.from_knowledge_graph, call.result_index, site)
    if locator is None:
        return [], [], None, [error]
    domain = domain_of(locator)
    claim = Claim(
        statement=(
            f"{domain or locator} is the official web presence of {legal_name}: {call.reasoning}"
        ),
        sources=[source_ref(locator, snippet, at)],
        confidence=call.confidence,
    )
    return [claim], [], domain, []


def _not_found(
    legal_name: str,
    judgement: CounterpartyJudgement,
    site: OfficialSiteEvidence,
    fallback: str,
    at: str,
) -> tuple[list[Claim], list[RiskSignal], str | None, list[str]]:
    """An absence is a finding too, and it cites the search that found nothing."""
    call = judgement.official_site
    reason = call.reasoning if call is not None else "the model returned no site judgement"
    claim = Claim(
        statement=(
            f"No result on this search identifies {legal_name} as a legal entity with its "
            f"own web presence: {reason}"
        ),
        sources=[source_ref(fallback, site.query, at)],
        confidence=call.confidence if call is not None else NO_JUDGEMENT_CONFIDENCE,
    )
    signal = RiskSignal(
        kind=SignalKind.ENTITY_NOT_FOUND,
        weight=signal_weight(ENTITY_NOT_FOUND_WEIGHT, claim.confidence),
        claim=claim,
    )
    return [claim], [signal], None, []


def _resolve_site(
    from_graph: bool, index: int | None, site: OfficialSiteEvidence
) -> tuple[str | None, str, str]:
    """Turn the model's pointer into a URL that was really fetched."""
    if from_graph:
        graph = site.knowledge_graph
        if graph is not None and graph.website:
            return graph.website, f"{graph.title or ''} {graph.description or ''}".strip(), ""
        return None, "", "the judgement cites a knowledge graph that carries no website"
    results = site.organic_results
    if index is None or not 0 <= index < len(results):
        return None, "", f"the judgement cites organic result {index}, which was not retrieved"
    item = results[index]
    if not item.link:
        return None, "", f"organic result {index} came back without a link to cite"
    return item.link, f"{item.title or ''} — {item.snippet or ''}".strip(" —"), ""
