"""The ledger. Every gate decision, allowed or denied, in the order it happened.

A denial that is never written down is indistinguishable from a call that was
never attempted, so the record is not a log line the caller may forget: the gate
wrapper writes here on both branches and returns afterwards.

The row shape is the audit_log table's own columns, so persistence is a dump
rather than a translation.
"""

from typing import Any

from autocurricula.core.harness.actions import PermissionDecision
from autocurricula.schemas.common import StrictBaseModel, utc_now
from pydantic import Field

ALLOW = PermissionDecision.ALLOW.value
DENY = PermissionDecision.DENY.value


class TraceEntry(StrictBaseModel):
    """One decision of the capability gate, addressed by run and sequence.

    ``capability`` is empty exactly when the tool resolved to none, which is the
    fail-closed case and the one an auditor should read first.
    """

    run_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    agent_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    capability: str = ""
    decision: str = Field(min_length=1)
    reasons: list[str] = Field(default_factory=list)
    recorded_at: str = Field(min_length=1)

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW

    def as_row(self) -> dict[str, Any]:
        """The row as the audit_log table declares it."""
        return self.model_dump(mode="json")


class RunTrace:
    """The append-only sequence of gate decisions taken during one run."""

    def __init__(self, run_id: str) -> None:
        if not run_id.strip():
            raise ValueError("a trace without a run id cannot be persisted or read back")
        self.run_id = run_id
        self.entries: list[TraceEntry] = []

    def record(
        self,
        agent_id: str,
        tool: str,
        capability: str,
        decision: str,
        reasons: list[str] | None = None,
    ) -> TraceEntry:
        """Append one decision and hand it back stamped with its sequence."""
        entry = TraceEntry(
            run_id=self.run_id,
            seq=len(self.entries),
            agent_id=agent_id,
            tool=tool,
            capability=capability,
            decision=decision,
            reasons=list(reasons or []),
            recorded_at=utc_now().isoformat(),
        )
        self.entries.append(entry)
        return entry

    @property
    def allowances(self) -> list[TraceEntry]:
        return [entry for entry in self.entries if entry.allowed]

    @property
    def denials(self) -> list[TraceEntry]:
        return [entry for entry in self.entries if not entry.allowed]

    def rows(self) -> list[dict[str, Any]]:
        return [entry.as_row() for entry in self.entries]

    def __len__(self) -> int:
        return len(self.entries)


__all__ = ["ALLOW", "DENY", "RunTrace", "TraceEntry"]
