"""What a trace row needs before it can be read by a person.

A `TraceEntry` is the audit row: an agent id, a tool, a decision. The roster
already knows what that agent is called and the capability table already knows
which powers are reserved to a person, so the page looks both up rather than
asking the runner to carry display text it would then have to keep in step.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from countersign.fleet.capabilities import is_human_only
from countersign.fleet.roster import FLEET
from countersign.orchestration.gate import HARNESS_ID
from countersign.orchestration.trace import TraceEntry

HARNESS_NAME = "Run harness"
UNMAPPED = "no capability"

AGENT_NAMES: dict[str, str] = {agent.agent_id: agent.display_name for agent in FLEET}


def agent_name(agent_id: str) -> str:
    if agent_id == HARNESS_ID:
        return HARNESS_NAME
    return AGENT_NAMES.get(agent_id, agent_id)


@dataclass(frozen=True)
class StepView:
    """One gate decision, ready to render."""

    ordinal: int
    agent_id: str
    display_name: str
    tool: str
    capability: str
    allowed: bool
    human_only: bool
    reasons: tuple[str, ...]
    recorded_at: str

    @property
    def status(self) -> str:
        return "ok" if self.allowed else "denied"

    @property
    def what(self) -> str:
        return f"{self.tool} → {self.capability or UNMAPPED}"

    @property
    def reason(self) -> str:
        return " ".join(self.reasons)


def step_view(ordinal: int, entry: TraceEntry) -> StepView:
    return StepView(
        ordinal=ordinal,
        agent_id=entry.agent_id,
        display_name=agent_name(entry.agent_id),
        tool=entry.tool,
        capability=entry.capability,
        allowed=entry.allowed,
        human_only=bool(entry.capability) and is_human_only(entry.capability),
        reasons=tuple(entry.reasons),
        recorded_at=entry.recorded_at,
    )


def step_views(entries: Iterable[TraceEntry]) -> list[StepView]:
    """Numbered in the order the gate decided, not in the order they are stored."""
    return [step_view(index, entry) for index, entry in enumerate(entries, start=1)]


__all__ = [
    "AGENT_NAMES",
    "HARNESS_NAME",
    "UNMAPPED",
    "StepView",
    "agent_name",
    "step_view",
    "step_views",
]
