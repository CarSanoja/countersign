"""COUNTERSIGN's orchestration: the run, the gate it goes through, and its record.

`run_assessment` is the whole surface. Everything else is exported because a
caller that wants to exercise one stage, inject one seam or read the trace
should not have to reach into a private module to do it.
"""

from countersign.orchestration.domain_sweep import DomainFinding, DomainSweep, sweep_lookalikes
from countersign.orchestration.evidence import build_bundle
from countersign.orchestration.gate import (
    HARNESS_GRANT,
    HARNESS_ID,
    authorize,
    grant_for,
    guarded,
    refuse,
)
from countersign.orchestration.pipeline import run_assessment
from countersign.orchestration.ports import AssessmentPorts, ResolvedPorts, RunConfig
from countersign.orchestration.result import AssessmentResult
from countersign.orchestration.sink import MemoryTraceSink, TraceSink, XanoTraceSink
from countersign.orchestration.stages import (
    SkippedStage,
    Stage,
    StageOutcome,
    StageStatus,
    credential_skip,
    missing_credentials,
)
from countersign.orchestration.state import RunState
from countersign.orchestration.trace import ALLOW, DENY, RunTrace, TraceEntry

__all__ = [
    "ALLOW",
    "DENY",
    "HARNESS_GRANT",
    "HARNESS_ID",
    "AssessmentPorts",
    "AssessmentResult",
    "DomainFinding",
    "DomainSweep",
    "MemoryTraceSink",
    "ResolvedPorts",
    "RunConfig",
    "RunState",
    "RunTrace",
    "SkippedStage",
    "Stage",
    "StageOutcome",
    "StageStatus",
    "TraceEntry",
    "TraceSink",
    "XanoTraceSink",
    "authorize",
    "build_bundle",
    "credential_skip",
    "grant_for",
    "guarded",
    "missing_credentials",
    "refuse",
    "run_assessment",
    "sweep_lookalikes",
]
