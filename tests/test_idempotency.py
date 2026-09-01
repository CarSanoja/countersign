"""One invoice, however many times it arrives, is one assessment and one envelope.

Nothing here reaches the network. The lookup is exercised against an httpx
MockTransport so the request shape is asserted rather than assumed, and the
pipeline tests stub the lookup and both vendor writes, because a duplicate-
detection test that spends a Foxit envelope to prove it saves one is worthless.
"""

import json

import httpx
import pytest
from autocurricula.tools.base import ToolResult

from countersign.orchestration import AssessmentPorts, MemoryTraceSink, Stage, stage_persist
from countersign.orchestration import pipeline as pipeline_module
from countersign.orchestration.idempotency import (
    PriorRun,
    UnreadableDocument,
    content_key,
    document_key,
    index_row,
    previous_run,
)
from countersign.schemas.evidence import Claim
from countersign.schemas.verdict import RiskLevel, RiskSignal, SignalKind, Verdict
from tests.orchestration_fixtures import (
    AT,
    SERP_SOURCE,
    configure_every_provider,
    demo_config,
    fake_ports,
)

FIRST_RUN = "countersign-first"
INVOICE_BYTES = b"%PDF-1.7 remit to LT12 3250 0000 0000 0001"

PRIOR_VERDICT = Verdict(
    run_id=FIRST_RUN,
    level=RiskLevel.HIGH,
    headline="Payment redirected onto a lookalike domain",
    signals=[
        RiskSignal(
            kind=SignalKind.CONFUSABLE_ALREADY_REGISTERED,
            weight=0.35,
            claim=Claim(
                statement="a confusable of the official domain is already registered",
                sources=[SERP_SOURCE],
                confidence=0.9,
            ),
        )
    ],
    recommended_action="Do not pay.",
    decided_at=AT,
)


def prior_for(key: str) -> PriorRun:
    return PriorRun(
        run_id=FIRST_RUN, document_key=key, verdict=PRIOR_VERDICT, recorded_at=AT, record_id=7
    )


def forbidden_ports() -> AssessmentPorts:
    """Every seam a reused run must not touch, wired to fail loudly if it does."""

    async def never(*args, **kwargs):
        raise AssertionError("a reused assessment must not call a provider")

    return AssessmentPorts(
        extract=never,
        verify=never,
        check_domains=never,
        synthesize=never,
        generate=never,
        prepare_envelope=never,
    )


def xano_env(monkeypatch) -> None:
    monkeypatch.setenv("XANO_TOKEN", "token")
    monkeypatch.setenv("XANO_INSTANCE_DOMAIN", "x22q-pprx-ni6s.n7e.xano.io")
    monkeypatch.setenv("XANO_WORKSPACE_ID", "1")
    monkeypatch.setenv("XANO_VENDOR_TABLE_ID", "3")


@pytest.fixture
def invoice(tmp_path):
    path = tmp_path / "invoice-2291.pdf"
    path.write_bytes(INVOICE_BYTES)
    return str(path)


@pytest.fixture
def vendor_writes(monkeypatch):
    """Both vendor writes captured in memory: the assessment row and the key row."""
    written: list[dict] = []

    async def persisted(vendor, content_id=""):
        written.append(vendor)
        return ToolResult.success({"data": vendor})

    monkeypatch.setattr(stage_persist, "xano_persist_vendor", persisted)
    monkeypatch.setattr(pipeline_module, "xano_persist_vendor", persisted)
    return written


def answer_lookup(monkeypatch, prior: PriorRun | None) -> list[str]:
    asked: list[str] = []

    async def lookup(key, **kwargs):
        asked.append(key)
        return prior

    monkeypatch.setattr(pipeline_module, "previous_run", lookup)
    return asked


def transport_returning(*rows: dict) -> tuple[httpx.MockTransport, list[dict]]:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content)})
        return httpx.Response(200, json={"items": list(rows)})

    return httpx.MockTransport(handler), seen


def test_the_same_bytes_under_different_names_are_one_document(tmp_path):
    first = tmp_path / "invoice-2291.pdf"
    second = tmp_path / "RE_ FW_ invoice (2).pdf"
    first.write_bytes(INVOICE_BYTES)
    second.write_bytes(INVOICE_BYTES)

    assert document_key(str(first)) == document_key(str(second))
    assert document_key(INVOICE_BYTES) == document_key(str(first))
    assert document_key(INVOICE_BYTES).startswith("sha256:")


def test_one_name_carrying_different_bytes_is_not_one_document(tmp_path):
    path = tmp_path / "invoice-2291.pdf"
    path.write_bytes(INVOICE_BYTES)
    first = document_key(str(path))
    path.write_bytes(INVOICE_BYTES.replace(b"LT12", b"DE89"))

    assert document_key(str(path)) != first


def test_a_reference_that_names_no_file_has_no_key_rather_than_a_name_key():
    with pytest.raises(UnreadableDocument):
        document_key("invoice-2291.pdf")
    assert content_key("invoice-2291.pdf") == ""


async def test_the_lookup_asks_for_the_newest_vendor_row_with_that_key(monkeypatch):
    xano_env(monkeypatch)
    row = index_row("sha256:abc", FIRST_RUN, "invoice-2291.pdf", PRIOR_VERDICT)
    transport, seen = transport_returning(row | {"id": 7, "created_at": 1788277583884})

    prior = await previous_run("sha256:abc", transport=transport)

    assert seen[0]["url"].endswith("/api:meta/workspace/1/table/3/content/search")
    assert seen[0]["body"]["search"] == {"document_key": "sha256:abc"}
    assert seen[0]["body"]["sort"] == {"id": "desc"}
    assert prior is not None
    assert prior.run_id == FIRST_RUN
    assert prior.verdict.level is RiskLevel.HIGH
    assert prior.verdict.signals[0].claim.sources[0].locator == SERP_SOURCE.locator
    assert prior.recorded_at.startswith("2026-")
    assert prior.record_id == 7


async def test_a_row_without_a_usable_verdict_is_not_a_prior_run(monkeypatch):
    """Silence is the one thing never reused: an absent or unreadable verdict sends
    the document back through the providers rather than answering from a ruin."""
    xano_env(monkeypatch)
    bare, _ = transport_returning({"id": 1, "run_id": FIRST_RUN, "evidence": None})
    corrupt, _ = transport_returning({"id": 2, "run_id": FIRST_RUN, "evidence": {"level": "hi"}})
    empty, _ = transport_returning()

    assert await previous_run("sha256:abc", transport=bare) is None
    assert await previous_run("sha256:abc", transport=corrupt) is None
    assert await previous_run("sha256:abc", transport=empty) is None


async def test_without_a_xano_credential_nothing_is_asked_and_nothing_is_reused(monkeypatch):
    monkeypatch.delenv("XANO_TOKEN", raising=False)

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the lookup must not leave the process without credentials")

    assert await previous_run("sha256:abc", transport=httpx.MockTransport(explode)) is None
    assert await previous_run("", transport=httpx.MockTransport(explode)) is None


async def test_a_second_run_of_the_same_invoice_prepares_no_second_envelope(
    monkeypatch, invoice, vendor_writes
):
    configure_every_provider(monkeypatch)
    key = document_key(invoice)
    asked = answer_lookup(monkeypatch, prior_for(key))
    sink = MemoryTraceSink()

    result = await pipeline_module.run_assessment(
        invoice, run_id="run-second", config=demo_config(), ports=forbidden_ports(), sink=sink
    )

    assert asked == [key]
    assert result.envelope == {}
    assert result.document == {}
    assert "foxit_prepare_envelope" not in [entry.tool for entry in result.trace]


async def test_a_high_verdict_is_reused_whole_rather_than_re_derived(
    monkeypatch, invoice, vendor_writes
):
    """The retry case that matters: a HIGH invoice must not raise a second signature
    request in front of the same person, and the verdict it is answered with keeps
    the signals it was grounded in."""
    configure_every_provider(monkeypatch)
    answer_lookup(monkeypatch, prior_for(document_key(invoice)))

    result = await pipeline_module.run_assessment(
        invoice,
        run_id="run-second",
        config=demo_config(),
        ports=forbidden_ports(),
        sink=MemoryTraceSink(),
    )

    assert result.verdict is not None
    assert result.verdict.level is RiskLevel.HIGH
    assert result.verdict.signals[0].claim.sources
    assert result.verdict.run_id == FIRST_RUN


async def test_the_reuse_is_on_the_record_as_a_decision_and_not_a_silence(
    monkeypatch, invoice, vendor_writes
):
    configure_every_provider(monkeypatch)
    answer_lookup(monkeypatch, prior_for(document_key(invoice)))
    sink = MemoryTraceSink()

    result = await pipeline_module.run_assessment(
        invoice, run_id="run-second", config=demo_config(), ports=forbidden_ports(), sink=sink
    )

    assert result.reused is True
    assert result.reused_from is not None
    assert result.reused_from.run_id == FIRST_RUN
    assert result.document_key == document_key(invoice)
    assert result.skipped_stages == list(pipeline_module.REUSED_STAGES)
    assert all(FIRST_RUN in entry.reason for entry in result.skipped)
    assert [entry.tool for entry in result.denials] == ["foxit_execute_signature"]
    assert Stage.PERSISTENCE in result.completed_stages
    assert len(sink.rows) == len(result.trace)


async def test_a_first_run_indexes_its_content_key_for_the_next_one(
    monkeypatch, invoice, vendor_writes
):
    configure_every_provider(monkeypatch)
    asked = answer_lookup(monkeypatch, None)
    sink = MemoryTraceSink()

    result = await pipeline_module.run_assessment(
        invoice, run_id="run-first", config=demo_config(), sink=sink, ports=fake_ports()
    )

    assert asked == [document_key(invoice)]
    assert result.reused is False
    indexed = [row for row in vendor_writes if row.get("document_key")]
    assert len(indexed) == 1
    assert indexed[0]["document_key"] == document_key(invoice)
    assert indexed[0]["run_id"] == "run-first"
    assert len(sink.rows) == len(result.trace)


async def test_the_indexed_row_reads_back_as_the_verdict_that_was_stored(monkeypatch):
    xano_env(monkeypatch)
    row = index_row("sha256:abc", FIRST_RUN, "invoice-2291.pdf", PRIOR_VERDICT)
    transport, _ = transport_returning(row | {"id": 7, "created_at": 1788277583884})

    prior = await previous_run("sha256:abc", transport=transport)

    assert prior is not None
    assert prior.verdict == PRIOR_VERDICT
    assert prior.summary.startswith(f"run {FIRST_RUN} (high, decided ")


async def test_reuse_off_never_asks_and_assesses_the_document_again(
    monkeypatch, invoice, vendor_writes
):
    configure_every_provider(monkeypatch)

    async def forbidden_lookup(key, **kwargs):
        raise AssertionError("reuse=False must not consult the index")

    monkeypatch.setattr(pipeline_module, "previous_run", forbidden_lookup)

    result = await pipeline_module.run_assessment(
        invoice,
        run_id="run-forced",
        config=demo_config(),
        ports=fake_ports(),
        sink=MemoryTraceSink(),
        reuse=False,
    )

    assert result.reused is False
    assert result.document_key == document_key(invoice)
    assert Stage.DELIVERY in result.completed_stages
    assert [row for row in vendor_writes if row.get("document_key")]
