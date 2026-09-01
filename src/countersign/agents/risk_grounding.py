"""The rule that defines this agent, written as code that can say no.

A verdict whose claims do not cite their span is rejected. Not annotated, not
downgraded, not flagged for a human to notice: rejected, and the draft is asked
for again.

The check that matters is the second one. A model can emit a citation whose
locator is a perfectly well formed URL and whose quote reads like a SERP
snippet, and the Claim schema will accept it, because the schema only knows
that a source is present. So every citation is resolved against the evidence
that was actually collected in this run, and the quote is matched against that
item's retrieved text with the framework's span verifier.
"""

from enum import StrEnum

from autocurricula.core.harness.faithfulness import DEFAULT_MATCH_THRESHOLD, span_status
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.telemetry import VERIFICATION_VERIFIED

from countersign.agents.risk_draft import DraftCitation, DraftSignal, DraftVerdict
from countersign.agents.risk_evidence import EvidenceBundle, EvidenceItem
from countersign.agents.risk_weights import deciding_providers
from countersign.schemas.evidence import SourceRef


class GroundingFailureKind(StrEnum):
    NO_CITATION = "no_citation"
    UNKNOWN_SOURCE = "unknown_source"
    EMPTY_QUOTE = "empty_quote"
    QUOTE_NOT_IN_EVIDENCE = "quote_not_in_evidence"
    WRONG_PROVIDER = "wrong_provider"
    MISSING_REQUIRED_SIGNAL = "missing_required_signal"


class GroundingFailure(StrictBaseModel):
    kind: GroundingFailureKind
    where: str
    detail: str

    def as_line(self) -> str:
        return f"- [{self.kind.value}] {self.where}: {self.detail}"


def check_draft(
    draft: DraftVerdict,
    bundle: EvidenceBundle,
    *,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[GroundingFailure]:
    """Every reason this draft is not publishable. Empty means it is."""
    index = bundle.index()
    failures: list[GroundingFailure] = []
    for position, signal in enumerate(draft.signals):
        failures.extend(_check_signal(signal, position, index, match_threshold))
    failures.extend(_check_required_signals(draft, bundle))
    return failures


def _check_signal(
    signal: DraftSignal,
    position: int,
    index: dict[str, EvidenceItem],
    match_threshold: float,
) -> list[GroundingFailure]:
    where = f"signals[{position}] ({signal.kind.value})"
    citations = signal.claim.citations
    if not citations:
        return [
            GroundingFailure(
                kind=GroundingFailureKind.NO_CITATION,
                where=where,
                detail="the claim cites no evidence; a claim without a span is not a claim",
            )
        ]
    failures: list[GroundingFailure] = []
    for offset, citation in enumerate(citations):
        cited_at = f"{where}.citations[{offset}]"
        failures.extend(_check_citation(citation, cited_at, index, match_threshold))
    failures.extend(_check_provider(signal, where, index))
    return failures


def _check_citation(
    citation: DraftCitation,
    where: str,
    index: dict[str, EvidenceItem],
    match_threshold: float,
) -> list[GroundingFailure]:
    item = index.get(citation.evidence_id)
    if item is None:
        return [
            GroundingFailure(
                kind=GroundingFailureKind.UNKNOWN_SOURCE,
                where=where,
                detail=(
                    f"{citation.evidence_id!r} was never collected in this run; "
                    f"known ids are {sorted(index)}"
                ),
            )
        ]
    quote = citation.quote.strip()
    if not quote:
        return [
            GroundingFailure(
                kind=GroundingFailureKind.EMPTY_QUOTE,
                where=where,
                detail=f"cites {item.evidence_id} but quotes nothing from it",
            )
        ]
    if span_status(quote, item.text, match_threshold=match_threshold) != VERIFICATION_VERIFIED:
        return [
            GroundingFailure(
                kind=GroundingFailureKind.QUOTE_NOT_IN_EVIDENCE,
                where=where,
                detail=f"the quoted span is not in the text collected as {item.evidence_id}",
            )
        ]
    return []


def _check_provider(
    signal: DraftSignal, where: str, index: dict[str, EvidenceItem]
) -> list[GroundingFailure]:
    allowed = deciding_providers(signal.kind)
    cited = {
        index[citation.evidence_id].provider
        for citation in signal.claim.citations
        if citation.evidence_id in index
    }
    if cited & allowed:
        return []
    return [
        GroundingFailure(
            kind=GroundingFailureKind.WRONG_PROVIDER,
            where=where,
            detail=(
                f"{signal.kind.value} is only established by "
                f"{sorted(p.value for p in allowed)}, and this claim cites "
                f"{sorted(p.value for p in cited)}"
            ),
        )
    ]


def _check_required_signals(
    draft: DraftVerdict, bundle: EvidenceBundle
) -> list[GroundingFailure]:
    raised = set(draft.kinds)
    return [
        GroundingFailure(
            kind=GroundingFailureKind.MISSING_REQUIRED_SIGNAL,
            where="signals",
            detail=(
                f"{kind.value} was already established by the deterministic sweep "
                "and the draft omits it"
            ),
        )
        for kind in bundle.required_signals
        if kind not in raised
    ]


def resolve_sources(
    citations: list[DraftCitation], index: dict[str, EvidenceItem]
) -> list[SourceRef]:
    """Build the Claim's sources from what was collected, not from the model.

    The provider, locator, box and timestamp come from the bundle; only the
    snippet comes from the draft, and only after it matched the collected text.
    """
    return [
        index[citation.evidence_id].source.model_copy(
            update={"snippet": citation.quote.strip()}
        )
        for citation in citations
        if citation.evidence_id in index
    ]
