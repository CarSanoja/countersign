"""The gate an agent asks before it uses a tool, and the record it leaves when refused.

Split out of the envelope preparer because it is a second responsibility and
because every agent in the fleet needs the same three checks: the tool must
resolve to a capability, the fleet must hold that capability, and this agent in
particular must have been granted it.

A denial is an object, not a log line. It travels back in the tool payload so
the audit trail and the UI can show which agent asked for what, and who is the
only one allowed to answer.
"""

from datetime import UTC, datetime

from autocurricula.schemas.common import StrictBaseModel

from countersign.fleet.capabilities import agent_holds, capability_for_tool, is_human_only

GATE = "capability gate"


class CapabilityDenial(StrictBaseModel):
    """One refused attempt, kept as evidence instead of discarded."""

    agent_id: str
    tool: str
    capability: str | None
    human_only: bool
    denied_by: str
    reason: str
    attempted_at: str


def denial(
    agent_id: str,
    tool: str,
    capability: str | None,
    denied_by: str,
    reason: str,
    human_only: bool,
) -> CapabilityDenial:
    """Stamp a refusal with the moment it happened."""
    return CapabilityDenial(
        agent_id=agent_id,
        tool=tool,
        capability=None if capability is None else str(capability),
        human_only=human_only,
        denied_by=denied_by,
        reason=reason,
        attempted_at=datetime.now(UTC).isoformat(),
    )


def gate(agent_id: str, tool: str, held: frozenset[str]) -> CapabilityDenial | None:
    """Refuse anything this agent was not granted. None means the call may proceed."""
    capability = capability_for_tool(tool)
    if capability is None:
        return denial(
            agent_id,
            tool,
            None,
            GATE,
            f"{tool} maps to no capability, so the gate fails closed",
            False,
        )
    human_only = is_human_only(capability)
    if not agent_holds(capability):
        only_a_person = ", only by a person" if human_only else ""
        return denial(
            agent_id,
            tool,
            capability,
            GATE,
            f"{capability} is held by no agent in the fleet{only_a_person}",
            human_only,
        )
    if str(capability) not in held:
        return denial(
            agent_id,
            tool,
            capability,
            GATE,
            f"{capability} is granted to the fleet but not to {agent_id}",
            human_only,
        )
    return None


__all__ = ["GATE", "CapabilityDenial", "denial", "gate"]
