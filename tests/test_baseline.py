"""The signal that decides a payment, exercised without spending a credit.

Every test here is about one distinction: what the document says about itself is
not the same fact as what this vendor's file holds. The Xano half runs against a
MockTransport, so the read is asserted on shape rather than on a live workspace.
"""

import httpx
import pytest

from countersign.agents.document_extractor import ExtractedField, ExtractedInvoice
from countersign.orchestration.baseline import (
    SALT_ENV,
    UNKNOWN_BASELINE_WEIGHT,
    BaselineUnavailable,
    VendorBaseline,
    bank_fingerprint,
    bank_signal,
    baseline_columns,
    baseline_configured,
    known_bank,
)
from countersign.orchestration.evidence import build_bundle
from countersign.schemas.evidence import PageBox, Provider, SourceRef
from countersign.schemas.verdict import SignalKind
from countersign.tools import xano

AT = "2026-09-01T10:00:00Z"
SINCE = "2026-03-04T09:00:00Z"
ON_FILE = "ES9121000418450200051332"
REDIRECTED = "LT123250000000000001"
VENDOR = "Acme Corp, S.L."

XANO_VARIABLES = (
    xano.TOKEN_ENV,
    xano.DOMAIN_ENV,
    xano.WORKSPACE_ENV,
    xano.VENDOR_TABLE_ENV,
)


@pytest.fixture(autouse=True)
def salted(monkeypatch):
    monkeypatch.setenv(SALT_ENV, "per-instance-secret")


def configure_xano(monkeypatch) -> None:
    monkeypatch.setenv(xano.TOKEN_ENV, "token")
    monkeypatch.setenv(xano.DOMAIN_ENV, "x22q.n7e.xano.io")
    monkeypatch.setenv(xano.WORKSPACE_ENV, "1")
    monkeypatch.setenv(xano.VENDOR_TABLE_ENV, "3")


def field(value: str, snippet: str) -> ExtractedField:
    return ExtractedField(
        value=value,
        span_id="s1",
        source=SourceRef(
            provider=Provider.NUTRIENT,
            locator="invoice-2291.pdf",
            box=PageBox(page=0, left=0.1, top=0.2, width=0.5, height=0.04),
            snippet=snippet,
            retrieved_at=AT,
        ),
    )


def invoice_paying(iban: str, *, announced: bool = False) -> ExtractedInvoice:
    return ExtractedInvoice(
        document_path="invoice-2291.pdf",
        extracted_at=AT,
        page_count=1,
        legal_name=field(VENDOR, f"{VENDOR} invoice 2291"),
        iban=field(iban, f"Remit to IBAN {iban}"),
        bank_change=(
            field("PLEASE NOTE OUR BANK", "PLEASE NOTE OUR BANK HAS CHANGED")
            if announced
            else None
        ),
    )


def on_file(fingerprint: str) -> VendorBaseline:
    return VendorBaseline(
        legal_name=VENDOR,
        fingerprint=fingerprint,
        since=SINCE,
        locator="https://x22q.n7e.xano.io/api:meta/workspace/1/table/3/content/160",
    )


def rows_transport(rows, status: int = 200, captured: list | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        if status != 200:
            return httpx.Response(status, text="upstream is down")
        return httpx.Response(status, json={"items": rows})

    return httpx.MockTransport(handle)


def test_the_fingerprint_ignores_how_the_account_was_typed():
    spaced = bank_fingerprint("ES91 2100 0418 4502 0005 1332")
    assert spaced == bank_fingerprint(ON_FILE)
    assert spaced == bank_fingerprint(ON_FILE.lower())
    assert spaced != bank_fingerprint(REDIRECTED)


def test_the_fingerprint_carries_none_of_the_account_and_none_of_it_survives_a_leak(monkeypatch):
    digest = bank_fingerprint(ON_FILE)
    assert "9121000418" not in digest
    assert not any(part in digest for part in (ON_FILE, ON_FILE.lower()))
    monkeypatch.setenv(SALT_ENV, "a-different-instance")
    assert bank_fingerprint(ON_FILE) != digest


def test_a_missing_salt_fails_by_name_rather_than_hashing_unsalted(monkeypatch):
    monkeypatch.delenv(SALT_ENV, raising=False)
    with pytest.raises(xano.MissingCredential) as raised:
        bank_fingerprint(ON_FILE)
    assert SALT_ENV in str(raised.value)


def test_an_account_with_no_content_has_no_fingerprint():
    with pytest.raises(ValueError):
        bank_fingerprint("   -- ")


def test_the_columns_a_first_sighting_writes_back():
    columns = baseline_columns(ON_FILE, AT)
    assert columns == {"bank_fingerprint": bank_fingerprint(ON_FILE), "bank_since": AT}


def test_the_comparison_is_off_until_both_xano_and_the_salt_are_present(monkeypatch):
    for variable in XANO_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    assert baseline_configured() is False
    configure_xano(monkeypatch)
    assert baseline_configured() is True
    monkeypatch.delenv(SALT_ENV)
    assert baseline_configured() is False


async def test_the_file_is_read_from_the_vendors_table_with_the_row_it_came_from(monkeypatch):
    configure_xano(monkeypatch)
    captured: list[httpx.Request] = []
    rows = [{"id": 160, "legal_name": VENDOR, "bank_fingerprint": "abc123", "bank_since": SINCE}]
    baseline = await known_bank(VENDOR, transport=rows_transport(rows, captured=captured))
    assert baseline is not None
    assert (baseline.fingerprint, baseline.since) == ("abc123", SINCE)
    assert baseline.locator.endswith("/workspace/1/table/3/content/160")
    assert captured[0].url.path == "/api:meta/workspace/1/table/3/content/search"


async def test_a_vendor_we_have_never_seen_is_absent_rather_than_an_error(monkeypatch):
    configure_xano(monkeypatch)
    rows = [{"id": 1, "legal_name": "Someone Else", "bank_fingerprint": "abc123"}]
    assert await known_bank(VENDOR, transport=rows_transport(rows)) is None


async def test_a_row_with_no_fingerprint_yet_is_not_a_file(monkeypatch):
    configure_xano(monkeypatch)
    rows = [{"id": 9, "legal_name": VENDOR, "bank_fingerprint": ""}]
    assert await known_bank(VENDOR, transport=rows_transport(rows)) is None


async def test_the_date_falls_back_to_the_rows_own_birthday(monkeypatch):
    configure_xano(monkeypatch)
    row = {"id": 3, "legal_name": VENDOR, "bank_fingerprint": "abc123"}
    rows = [{**row, "created_at": 1788277583884}]
    baseline = await known_bank(VENDOR, transport=rows_transport(rows))
    assert baseline is not None
    assert baseline.since.startswith("2026-")


async def test_a_read_that_broke_is_not_reported_as_a_vendor_we_never_saw(monkeypatch):
    configure_xano(monkeypatch)
    with pytest.raises(BaselineUnavailable):
        await known_bank(VENDOR, transport=rows_transport([], status=500))


async def test_the_lookup_names_the_credential_it_is_missing(monkeypatch):
    configure_xano(monkeypatch)
    monkeypatch.delenv(xano.VENDOR_TABLE_ENV)
    with pytest.raises(xano.MissingCredential) as raised:
        await known_bank(VENDOR, transport=rows_transport([]))
    assert xano.VENDOR_TABLE_ENV in str(raised.value)


def test_an_account_that_is_not_the_one_on_file_is_the_signal_and_cites_both_halves():
    baseline = on_file(bank_fingerprint(ON_FILE))
    signal = bank_signal(invoice_paying(REDIRECTED), baseline, AT)
    assert signal is not None
    assert signal.kind is SignalKind.BANK_DETAILS_CHANGED
    assert signal.weight == pytest.approx(0.45)
    providers = [source.provider for source in signal.claim.sources]
    assert providers == [Provider.XANO, Provider.NUTRIENT]
    assert SINCE in signal.claim.statement
    assert ON_FILE not in signal.claim.sources[0].snippet


def test_the_document_does_not_have_to_announce_the_change_for_it_to_be_one():
    baseline = on_file(bank_fingerprint(ON_FILE))
    silent = invoice_paying(REDIRECTED)
    assert silent.bank_change is None
    assert bank_signal(silent, baseline, AT) is not None


def test_announcing_a_change_to_the_account_already_on_file_is_not_a_signal():
    baseline = on_file(bank_fingerprint(ON_FILE))
    loud = invoice_paying(ON_FILE, announced=True)
    assert loud.bank_change is not None
    assert bank_signal(loud, baseline, AT) is None


def test_a_vendor_with_no_file_gets_the_weaker_answer_and_says_it_does_not_know():
    signal = bank_signal(invoice_paying(REDIRECTED), None, AT)
    assert signal is not None
    assert signal.weight == pytest.approx(UNKNOWN_BASELINE_WEIGHT)
    assert signal.weight < 0.45
    assert "nothing to compare" in signal.claim.statement
    assert [source.provider for source in signal.claim.sources] == [Provider.NUTRIENT]


def test_an_invoice_that_prints_no_account_says_nothing_about_accounts():
    without = ExtractedInvoice(document_path="x.pdf", extracted_at=AT, page_count=1)
    assert bank_signal(without, on_file("abc123"), AT) is None
    assert bank_signal(without, None, AT) is None


def test_the_bundle_stays_silent_when_the_file_agrees_and_the_page_shouts(monkeypatch):
    configure_xano(monkeypatch)
    bundle = build_bundle(
        "run-1",
        VENDOR,
        invoice=invoice_paying(ON_FILE, announced=True),
        baseline=on_file(bank_fingerprint(ON_FILE)),
    )
    assert bundle is not None
    assert SignalKind.BANK_DETAILS_CHANGED not in [s.kind for s in bundle.established_signals]


def test_the_bundle_raises_the_signal_when_the_file_disagrees(monkeypatch):
    configure_xano(monkeypatch)
    bundle = build_bundle(
        "run-2",
        VENDOR,
        invoice=invoice_paying(REDIRECTED),
        baseline=on_file(bank_fingerprint(ON_FILE)),
    )
    assert bundle is not None
    signals = {signal.kind: signal for signal in bundle.established_signals}
    assert signals[SignalKind.BANK_DETAILS_CHANGED].weight == pytest.approx(0.45)


def test_without_xano_the_bundle_falls_back_to_the_phrase_and_admits_it(monkeypatch):
    for variable in XANO_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    bundle = build_bundle("run-3", VENDOR, invoice=invoice_paying(REDIRECTED, announced=True))
    assert bundle is not None
    signals = {signal.kind: signal for signal in bundle.established_signals}
    statement = signals[SignalKind.BANK_DETAILS_CHANGED].claim.statement
    assert "No vendor file is configured" in statement


def test_without_xano_a_silent_document_still_raises_nothing(monkeypatch):
    for variable in XANO_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    bundle = build_bundle("run-4", VENDOR, invoice=invoice_paying(REDIRECTED))
    assert bundle is not None
    assert bundle.established_signals == []
