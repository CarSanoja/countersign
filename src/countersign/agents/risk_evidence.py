"""The evidence a verdict is allowed to rest on, and nothing else.

The synthesiser never receives a free-text dossier. It receives an index of
items that were actually collected, each addressable by id, and it may only
cite those ids. A source the model invents cannot resolve against this index,
which is what turns "claims must cite their span" into something enforceable
rather than something asked for in a prompt.
"""

from enum import StrEnum

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field, model_validator

from countersign.schemas.evidence import Provider, SourceRef
from countersign.schemas.verdict import RiskSignal, SignalKind


class EvidenceChannel(StrEnum):
    """Which stage of the pipeline produced the item."""

    EXTRACTION = "extraction"
    VERIFICATION = "verification"
    DOMAIN_SWEEP = "domain_sweep"
    BACKEND = "backend"


class EvidenceItem(StrictBaseModel):
    """One collected fact, with the exact text a claim is allowed to quote.

    `text` is the retrieved material verbatim: the page span Nutrient returned,
    the SERP snippet, the registry answer. It is the only corpus a quote is
    checked against.
    """

    evidence_id: str = Field(min_length=1)
    channel: EvidenceChannel
    text: str = Field(min_length=1)
    source: SourceRef

    @property
    def provider(self) -> Provider:
        return self.source.provider

    @property
    def page(self) -> int | None:
        return None if self.source.box is None else self.source.box.page


class EvidenceBundle(StrictBaseModel):
    """Everything the fleet gathered about one counterparty, in one run.

    `required_signals` carries the kinds the deterministic layer already
    established, typically the domain sweep. A draft that omits one of them is
    under-reporting a fact nobody had to judge, and is rejected like any other
    grounding failure.
    """

    run_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    items: list[EvidenceItem] = Field(min_length=1)
    required_signals: list[SignalKind] = Field(default_factory=list)
    suppressed_signals: list[SignalKind] = Field(default_factory=list)
    """Kinds the pipeline settled as not applicable to this document.

    Standing brand exposure is the case: every well-known vendor has confusable
    variants registered, so scoring it against an invoice that genuinely came
    from the official domain would mark every real invoice for review. The model
    can still read the finding in the evidence; it may not raise it as a signal.
    """
    established_signals: list[RiskSignal] = Field(default_factory=list)
    """Signals already settled deterministically upstream.

    A sender domain that differs from the official one is a string comparison,
    not a judgement. Leaving it for the model to re-derive from prose is how the
    same invoice scored HIGH on one run and REVIEW on the next, so these are
    carried through and take precedence over the model's version of the same
    kind."""

    @model_validator(mode="after")
    def _ids_are_unique(self):
        seen: set[str] = set()
        for item in self.items:
            if item.evidence_id in seen:
                raise ValueError(f"duplicate evidence id {item.evidence_id!r}")
            seen.add(item.evidence_id)
        return self

    def index(self) -> dict[str, EvidenceItem]:
        return {item.evidence_id: item for item in self.items}

    def by_channel(self, channel: EvidenceChannel) -> list[EvidenceItem]:
        return [item for item in self.items if item.channel == channel]

    @property
    def evidence_ids(self) -> list[str]:
        return [item.evidence_id for item in self.items]
