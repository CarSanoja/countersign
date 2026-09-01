"""What one run hands back: the verdict, the whole trace, and what it could not do.

The three travel together on purpose. A verdict without the trace cannot be
audited, and a trace without the skipped stages reads as a complete assessment
when it may have been missing a provider the whole way through.

A reused verdict is the fourth thing that has to travel with them. ``reused_from``
names the run whose assessment this one is quoting, so a caller can never mistake
a quotation for a fresh judgement, and ``document_key`` says what the two runs
have in common: the bytes, not the file name.
"""

from typing import Any

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

from countersign.orchestration.idempotency import PriorRun
from countersign.orchestration.stages import SkippedStage, Stage, StageOutcome, StageStatus
from countersign.orchestration.trace import TraceEntry
from countersign.schemas.verdict import Verdict


class AssessmentResult(StrictBaseModel):
    """The outcome of one document, complete or partial, and readable either way."""

    run_id: str = Field(min_length=1)
    document_ref: str = Field(min_length=1)
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    verdict: Verdict | None = None
    trace: list[TraceEntry] = Field(default_factory=list)
    skipped: list[SkippedStage] = Field(default_factory=list)
    stages: list[StageOutcome] = Field(default_factory=list)
    document: dict[str, Any] = Field(default_factory=dict)
    envelope: dict[str, Any] = Field(default_factory=dict)
    trace_persisted: bool = False
    errors: list[str] = Field(default_factory=list)
    document_key: str = Field(
        default="",
        description="sha256 of the assessed bytes; empty when the reference was unreadable "
        "and duplicate detection was therefore off for this run",
    )
    reused_from: PriorRun | None = Field(
        default=None,
        description="the earlier run this verdict was quoted from, when nothing was re-run",
    )

    @property
    def denials(self) -> list[TraceEntry]:
        return [entry for entry in self.trace if not entry.allowed]

    @property
    def skipped_stages(self) -> list[Stage]:
        return [entry.stage for entry in self.skipped]

    @property
    def completed_stages(self) -> list[Stage]:
        return [
            outcome.stage
            for outcome in self.stages
            if outcome.status in (StageStatus.COMPLETED, StageStatus.DEGRADED)
        ]

    @property
    def reached_a_verdict(self) -> bool:
        return self.verdict is not None

    @property
    def reused(self) -> bool:
        """True when no provider was charged because this content was already assessed."""
        return self.reused_from is not None


__all__ = ["AssessmentResult"]
