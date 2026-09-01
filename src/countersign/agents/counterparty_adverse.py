"""Adverse coverage of this entity, kept apart from coverage of its namesakes.

A dismissed namesake is not discarded: it comes back as a claim of its own, so
the report can show which lawsuit was seen and why it was not counted. Silence
about a dismissal is indistinguishable from never having looked.
"""

from countersign.agents.counterparty_claims import signal_weight, source_ref
from countersign.agents.counterparty_evidence import CounterpartyEvidence, archive_locator
from countersign.agents.counterparty_judgement import (
    AdverseCategory,
    CounterpartyJudgement,
    NewsJudgement,
)
from countersign.schemas.evidence import Claim, SourceRef
from countersign.schemas.verdict import RiskSignal, SignalKind
from countersign.tools.serpapi_models import NewsItem

ADVERSE_WEIGHT: dict[AdverseCategory, float] = {
    AdverseCategory.SANCTIONS: 0.95,
    AdverseCategory.FRAUD: 0.85,
    AdverseCategory.INSOLVENCY: 0.75,
    AdverseCategory.REGULATORY: 0.6,
    AdverseCategory.LITIGATION: 0.5,
    AdverseCategory.OTHER: 0.35,
}
DEFAULT_ADVERSE_WEIGHT = 0.35


def _item_source(item: NewsItem, fallback: str, at: str) -> SourceRef:
    """Cite the article itself; fall back to the SERP only when it carried no link."""
    snippet = f"{item.title or ''} — {item.source_name or ''} — {item.iso_date or ''}"
    return source_ref(item.link or fallback, snippet.strip(" —"), at)


def adverse_media_findings(
    legal_name: str, judgement: CounterpartyJudgement, evidence: CounterpartyEvidence, at: str
) -> tuple[list[RiskSignal], list[Claim], list[str]]:
    """Signals for this entity, dismissals for the rest, errors for bad pointers."""
    news = evidence.adverse_media
    if news is None:
        return [], [], []
    fallback = archive_locator(news.search_id, news.query)
    signals: list[RiskSignal] = []
    dismissed: list[Claim] = []
    errors: list[str] = []
    for call in judgement.news:
        if not 0 <= call.item_index < len(news.items):
            errors.append(
                f"the judgement cites news item {call.item_index}, which was not retrieved"
            )
            continue
        if not call.adverse:
            continue
        source = _item_source(news.items[call.item_index], fallback, at)
        if not call.same_entity:
            dismissed.append(_dismissal(legal_name, call.entity_reasoning, call.confidence, source))
            continue
        signals.append(_signal(legal_name, news.items[call.item_index], call, source))
    return signals, dismissed, errors


def _dismissal(legal_name: str, reasoning: str, confidence: float, source: SourceRef) -> Claim:
    return Claim(
        statement=(
            f"This coverage concerns a different legal entity than {legal_name} and is not "
            f"counted against it: {reasoning}"
        ),
        sources=[source],
        confidence=confidence,
    )


def _signal(
    legal_name: str, item: NewsItem, call: NewsJudgement, source: SourceRef
) -> RiskSignal:
    category = call.category or AdverseCategory.OTHER
    claim = Claim(
        statement=(
            f"{legal_name} is the subject of {category.value} coverage "
            f"({item.title or 'untitled report'}, {item.source_name or 'unattributed source'}): "
            f"{call.entity_reasoning}"
        ),
        sources=[source],
        confidence=call.confidence,
    )
    return RiskSignal(
        kind=SignalKind.ADVERSE_MEDIA,
        weight=signal_weight(
            ADVERSE_WEIGHT.get(category, DEFAULT_ADVERSE_WEIGHT), call.confidence
        ),
        claim=claim,
    )
