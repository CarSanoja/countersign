"""The boundary is the product claim, so it is asserted, not documented."""

import pytest

from countersign.fleet.capabilities import (
    AGENT_CAPABILITIES,
    HUMAN_ONLY_CAPABILITIES,
    TOOL_CAPABILITY,
    CountersignCapability,
    agent_holds,
    capability_for_tool,
)
from countersign.fleet.roster import FLEET


def test_no_agent_holds_a_human_only_capability():
    for agent in FLEET:
        overlap = set(agent.capabilities) & HUMAN_ONLY_CAPABILITIES
        assert not overlap, f"{agent.agent_id} was granted {overlap}"


def test_granted_and_human_only_sets_are_disjoint():
    assert not (AGENT_CAPABILITIES & HUMAN_ONLY_CAPABILITIES)


@pytest.mark.parametrize(
    "tool", ["foxit_execute_signature", "release_payment"]
)
def test_signing_and_payment_tools_resolve_to_a_capability_no_agent_holds(tool):
    capability = capability_for_tool(tool)
    assert capability is not None, "the tool must be mapped so a denial can be recorded"
    assert not agent_holds(capability)


def test_an_undeclared_tool_fails_closed():
    assert capability_for_tool("some_tool_nobody_declared") is None


def test_every_declared_tool_maps_to_a_known_capability():
    known = set(CountersignCapability)
    for tool, capability in TOOL_CAPABILITY.items():
        assert capability in known, f"{tool} maps to unknown capability {capability}"


def test_every_agent_capability_is_declared_in_the_enum():
    known = set(CountersignCapability)
    for agent in FLEET:
        for capability in agent.capabilities:
            assert capability in known, f"{agent.agent_id} holds undeclared {capability}"
