"""No tool call leaves this package without asking the gate first.

The three checks are the ones the fleet already declares: the tool must resolve
to a capability, the fleet must hold that capability, and this particular agent
must have been granted it. An unmapped tool resolves to None and is denied, so a
name nobody thought to map cannot be exercised by being misspelled.

The harness principal is not a fleet agent and is not in the roster. It writes
the ledger, and it is given the two backend capabilities explicitly here rather
than by editing the roster, so the seven agents keep the grants they were
designed with and the writer of the audit trail is visible as a separate
principal in the trail itself.
"""

from collections.abc import Awaitable, Callable

from autocurricula.tools.base import ToolResult

from countersign.agents.capability_gate import CapabilityDenial, gate
from countersign.fleet.capabilities import CountersignCapability as Cap
from countersign.fleet.capabilities import capability_for_tool
from countersign.fleet.roster import grants
from countersign.orchestration.trace import ALLOW, DENY, RunTrace

HARNESS_ID = "countersign-harness"
HARNESS_GRANT: frozenset[str] = frozenset(
    {str(Cap.BACKEND_PERSIST), str(Cap.BACKEND_READ)}
)

ToolCall = Callable[[], Awaitable[ToolResult]]


def grant_for(agent_id: str) -> frozenset[str]:
    """The capabilities this principal holds, read from the roster it belongs to."""
    if agent_id == HARNESS_ID:
        return HARNESS_GRANT
    return frozenset(str(capability) for capability in grants().get(agent_id, frozenset()))


def authorize(trace: RunTrace, agent_id: str, tool: str) -> CapabilityDenial | None:
    """Decide, record the decision either way, and hand back the refusal or None."""
    refusal = gate(agent_id, tool, grant_for(agent_id))
    if refusal is None:
        capability = capability_for_tool(tool)
        trace.record(agent_id, tool, str(capability or ""), ALLOW)
        return None
    trace.record(agent_id, tool, refusal.capability or "", DENY, [refusal.reason])
    return refusal


def denial_result(tool: str, refusal: CapabilityDenial) -> ToolResult:
    """A refusal expressed as a tool failure, carrying the denial as evidence."""
    return ToolResult(
        ok=False,
        error=f"{tool} denied: {refusal.reason}",
        payload={"denials": [refusal.model_dump(mode="json")]},
    )


async def guarded(trace: RunTrace, agent_id: str, tool: str, call: ToolCall) -> ToolResult:
    """Run the call only if the gate allows it. A denial never reaches the network."""
    refusal = authorize(trace, agent_id, tool)
    if refusal is not None:
        return denial_result(tool, refusal)
    return await call()


def refuse(trace: RunTrace, agent_id: str, tool: str) -> CapabilityDenial | None:
    """Evaluate a power on the record without exercising it.

    Used for the boundary the fleet is built around: the envelope preparer asks
    for signature.execute at every run so the refusal appears in the trail, and
    a power never asked for would leave no trace of being unavailable.
    """
    return authorize(trace, agent_id, tool)


__all__ = [
    "HARNESS_GRANT",
    "HARNESS_ID",
    "authorize",
    "denial_result",
    "grant_for",
    "guarded",
    "refuse",
]
