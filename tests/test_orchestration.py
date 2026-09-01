"""The two claims that make this an orchestration rather than a script.

Every tool call is authorised before it happens, and every decision is written
down. Both are asserted against a run where nothing reaches the network, because
a trace that can only be produced by spending a SerpApi credit is a trace nobody
will reproduce.
"""

import json

import httpx
import pytest
from autocurricula.tools.base import ToolResult

from countersign.orchestration import (
    HARNESS_ID,
    MemoryTraceSink,
    RunTrace,
    Stage,
    StageStatus,
    XanoTraceSink,
    authorize,
    run_assessment,
    stage_persist,
)
from countersign.schemas.verdict import RiskLevel
from tests.orchestration_fixtures import (
    configure_every_provider,
    demo_config,
    fake_ports,
    unconfigure_every_provider,
)


@pytest.fixture
def no_vendor_write(monkeypatch):
    async def persisted(vendor, content_id=""):
        return ToolResult.success({"data": vendor})

    monkeypatch.setattr(stage_persist, "xano_persist_vendor", persisted)


async def run(monkeypatch, **kwargs):
    sink = MemoryTraceSink()
    result = await run_assessment(
        "invoice-2291.pdf",
        run_id=kwargs.pop("run_id", "run-test"),
        config=kwargs.pop("config", demo_config()),
        ports=kwargs.pop("ports", fake_ports()),
        sink=sink,
    )
    return result, sink


async def test_a_full_run_records_one_gate_decision_per_tool_call(monkeypatch, no_vendor_write):
    configure_every_provider(monkeypatch)
    result, sink = await run(monkeypatch)

    assert result.verdict is not None
    assert result.verdict.level is RiskLevel.HIGH
    assert [entry.tool for entry in result.trace] == [
        "nutrient_extract_fields",
        "serpapi_find_official_site",
        "serpapi_adverse_media",
        "serpapi_verify_address",
        "namecom_check_availability",
        "doctavian_generate_document",
        "foxit_execute_signature",
        "foxit_prepare_envelope",
        "xano_persist_vendor",
        "xano_append_audit",
    ]
    assert [entry.seq for entry in result.trace] == list(range(len(result.trace)))
    assert all(entry.run_id == "run-test" for entry in result.trace)
    assert len(sink.rows) == len(result.trace)


async def test_the_signature_is_asked_for_every_run_and_refused(monkeypatch, no_vendor_write):
    configure_every_provider(monkeypatch)
    result, _ = await run(monkeypatch)

    refused = result.denials
    assert [entry.tool for entry in refused] == ["foxit_execute_signature"]
    assert refused[0].capability == "signature.execute"
    assert "no agent in the fleet" in refused[0].reasons[0]
    assert result.envelope["dispatched"] is False


async def test_a_tool_that_maps_to_no_capability_is_denied_and_recorded():
    trace = RunTrace("run-closed")
    refusal = authorize(trace, "document-extractor", "nutrient_exfiltrate")

    assert refusal is not None
    assert trace.entries[0].capability == ""
    assert trace.entries[0].decision == "deny"
    assert "fails closed" in trace.entries[0].reasons[0]


async def test_a_missing_key_costs_its_stage_and_not_the_run(monkeypatch, no_vendor_write):
    configure_every_provider(monkeypatch)
    monkeypatch.delenv("NAMECOM_TOKEN")
    result, _ = await run(monkeypatch)

    skipped = {entry.stage: entry for entry in result.skipped}
    assert skipped[Stage.DOMAIN].missing_variables == ["NAMECOM_TOKEN"]
    assert Stage.DOMAIN not in result.completed_stages
    assert result.verdict is not None
    assert "namecom_check_availability" not in [entry.tool for entry in result.trace]


async def test_with_no_provider_configured_the_run_still_answers(monkeypatch):
    unconfigure_every_provider(monkeypatch)
    result, sink = await run(monkeypatch)

    assert result.verdict is None
    assert result.skipped_stages == [
        Stage.INGEST,
        Stage.IDENTITY,
        Stage.DOMAIN,
        Stage.RISK,
        Stage.GENERATION,
        Stage.DELIVERY,
        Stage.PERSISTENCE,
    ]
    assert [entry.tool for entry in result.trace] == ["foxit_execute_signature"]
    assert sink.rows == []


async def test_an_exploding_stage_is_recorded_and_the_run_continues(monkeypatch, no_vendor_write):
    configure_every_provider(monkeypatch)

    async def explode(document_ref):
        raise RuntimeError("nutrient fell over")

    result, _ = await run(monkeypatch, ports=fake_ports(extract=explode))

    ingest = next(o for o in result.stages if o.stage is Stage.INGEST)
    assert ingest.status is StageStatus.FAILED
    assert "nutrient fell over" in ingest.detail
    assert Stage.PERSISTENCE in result.completed_stages


async def test_the_trace_reaches_xano_as_the_audit_log_columns(monkeypatch):
    monkeypatch.setenv("XANO_TOKEN", "token")
    monkeypatch.setenv("XANO_INSTANCE_DOMAIN", "x22q-pprx-ni6s.n7e.xano.io")
    monkeypatch.setenv("XANO_WORKSPACE_ID", "1")
    monkeypatch.setenv("XANO_AUDIT_TABLE_ID", "4")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    trace = RunTrace("run-persisted")
    authorize(trace, HARNESS_ID, "xano_append_audit")
    written = await XanoTraceSink(transport=httpx.MockTransport(handler)).write(trace.rows())

    assert written.ok
    assert seen["url"].startswith(
        "https://x22q-pprx-ni6s.n7e.xano.io/api:meta/workspace/1/table/4/content"
    )
    assert sorted(seen["body"]["items"][0]) == [
        "agent_id",
        "capability",
        "decision",
        "reasons",
        "recorded_at",
        "run_id",
        "seq",
        "tool",
    ]


async def test_a_missing_xano_variable_is_named_rather_than_raised(monkeypatch):
    unconfigure_every_provider(monkeypatch)
    trace = RunTrace("run-unpersisted")
    authorize(trace, HARNESS_ID, "xano_append_audit")

    written = await XanoTraceSink().write(trace.rows())

    assert not written.ok
    assert "XANO_INSTANCE_DOMAIN" in (written.error or "")
