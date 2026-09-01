"""The mutable middle of a run, passed from stage to stage.

Every stage reads what the ones before it produced and writes what it produced,
and none of them return early on a failure: a stage that cannot run records why
and leaves its slot empty, so the next stage decides for itself whether it can
proceed without that input.
"""

from dataclasses import dataclass, field
from typing import Any

from countersign.agents.counterparty_verifier import CounterpartyAssessment
from countersign.agents.document_extractor import ExtractedInvoice
from countersign.orchestration.domain_sweep import DomainSweep
from countersign.orchestration.ports import ResolvedPorts, RunConfig
from countersign.orchestration.stages import (
    SkippedStage,
    Stage,
    StageOutcome,
    StageStatus,
    credential_skip,
)
from countersign.orchestration.trace import RunTrace
from countersign.schemas.verdict import Verdict


@dataclass
class RunState:
    """Everything one run knows so far, and everything it failed to learn."""

    run_id: str
    document_ref: str
    config: RunConfig
    ports: ResolvedPorts
    trace: RunTrace
    started_at: str
    invoice: ExtractedInvoice | None = None
    assessment: CounterpartyAssessment | None = None
    sweep: DomainSweep | None = None
    verdict: Verdict | None = None
    document: dict[str, Any] = field(default_factory=dict)
    envelope: dict[str, Any] = field(default_factory=dict)
    trace_persisted: bool = False
    skipped: list[SkippedStage] = field(default_factory=list)
    outcomes: list[StageOutcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def skip(self, entry: SkippedStage) -> None:
        """Record a stage that was not attempted, and why."""
        self.skipped.append(entry)
        self.outcomes.append(
            StageOutcome(stage=entry.stage, status=StageStatus.SKIPPED, detail=entry.reason)
        )

    def blocked_by_credentials(self, stage: Stage) -> bool:
        """True when a provider key is missing, having recorded the skip."""
        entry = credential_skip(stage)
        if entry is None:
            return False
        self.skip(entry)
        return True

    def completed(self, stage: Stage, detail: str, errors: list[str] | None = None) -> None:
        status = StageStatus.DEGRADED if errors else StageStatus.COMPLETED
        self.outcomes.append(
            StageOutcome(stage=stage, status=status, detail=detail, errors=list(errors or []))
        )

    def failed(self, stage: Stage, error: str) -> None:
        self.errors.append(f"{stage.value}: {error}")
        self.outcomes.append(
            StageOutcome(stage=stage, status=StageStatus.FAILED, detail=error, errors=[error])
        )

    @property
    def legal_name(self) -> str:
        """The name to verify: what the document says, or what the caller supplied."""
        if self.invoice is not None and self.invoice.legal_name is not None:
            return self.invoice.legal_name.value
        return self.config.legal_name.strip()

    @property
    def address(self) -> str:
        if self.invoice is not None and self.invoice.address is not None:
            return self.invoice.address.value
        return self.config.address.strip()

    @property
    def sender_domain(self) -> str:
        if self.invoice is not None and self.invoice.sender_domain is not None:
            return self.invoice.sender_domain.value
        return self.config.sender_domain.strip()

    @property
    def official_domain(self) -> str:
        if self.assessment is not None and self.assessment.official_domain:
            return self.assessment.official_domain
        return self.config.official_domain.strip()


__all__ = ["RunState"]
