"""The Processor call and the page size, exercised without spending a credit."""

import httpx
import pytest
from document_extractor_fixtures import (
    FAITHFUL_ANSWER,
    PAGE_SIZE,
    FakeModel,
    json_content_body,
    minimal_pdf,
)

from countersign.agents.document_extractor import extract_invoice
from countersign.agents.document_extractor_layout import parse_layout
from countersign.agents.document_extractor_nutrient import build_instructions, fetch_layout
from countersign.agents.document_extractor_pagesize import page_size_from_pdf
from countersign.tools import nutrient_client


@pytest.fixture
def document(tmp_path):
    path = tmp_path / "acme-invoice.pdf"
    path.write_bytes(minimal_pdf())
    return str(path)


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


@pytest.fixture(autouse=True)
def mocked_nutrient(monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request]):
    monkeypatch.setenv("NUTRIENT_PROCESSOR_KEY", "pdf_live_test")
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json=json_content_body(), headers={"x-pspdfkit-request-cost": "3"}
        )

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(nutrient_client.httpx, "AsyncClient", factory)


def test_the_request_asks_for_json_content_after_ocr():
    instructions = build_instructions("spanish")
    assert instructions["output"] == {
        "type": "json-content",
        "plainText": True,
        "structuredText": True,
    }
    assert instructions["actions"][0]["type"] == "ocr"
    assert instructions["parts"] == [{"file": "document"}]
    assert build_instructions(None)["actions"] == []


async def test_fetch_layout_posts_the_document_and_locates_every_span(document, seen):
    result = await fetch_layout(document)
    assert result.ok, result.error
    assert seen[0].url.path == "/build"
    assert result.payload["span_count"] == 6
    assert result.payload["spans_without_a_box"] == 0
    assert result.payload["page_size"] == [612.0, 792.0]
    assert result.payload["page_size_source"] == "pdf-mediabox"
    assert result.payload["credit_cost"] == "3"


async def test_a_document_of_unknown_size_yields_spans_without_boxes(tmp_path):
    path = tmp_path / "sizeless.pdf"
    path.write_bytes(b"%PDF-1.4\ntrailer<</Root 1 0 R>>\n%%EOF\n")
    result = await fetch_layout(str(path))
    assert result.ok, result.error
    assert result.payload["page_size_source"] == "unknown"
    assert result.payload["spans_without_a_box"] == result.payload["span_count"] == 6


async def test_the_whole_agent_runs_without_a_live_model(document):
    result = await extract_invoice(document, FakeModel(FAITHFUL_ANSWER))
    assert result.ok, result.error
    assert result.payload["present_fields"] == [
        "legal_name",
        "address",
        "iban",
        "routing_number",
        "total_amount",
        "invoice_number",
        "sender_domain",
    ]
    assert result.payload["missing_fields"] == ["account_number"]


async def test_a_missing_key_names_the_variable_instead_of_raising(
    document, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("NUTRIENT_PROCESSOR_KEY", raising=False)
    result = await fetch_layout(document)
    assert not result.ok
    assert "NUTRIENT_PROCESSOR_KEY" in (result.error or "")


def test_a_line_carries_no_text_of_its_own_so_it_is_built_from_its_words():
    layout = parse_layout("/tmp/x.pdf", json_content_body(), page_size=PAGE_SIZE)
    assert [span.span_id for span in layout.spans][:2] == ["p0l0", "p0l1"]
    assert layout.spans[0].text == "ACME CORP S.L."
    assert layout.spans[2].text == "IBAN: ES91 2100 0418 4502 0005 1332"
    assert layout.spans[0].ocr_confidence is not None


def test_a_page_with_no_lines_falls_back_to_plain_text_without_geometry():
    body = {"pages": [{"plainText": "ACME CORP S.L.\n\nCalle Mayor 1\n"}]}
    layout = parse_layout("/tmp/x.pdf", body, page_size=PAGE_SIZE)
    assert [span.text for span in layout.spans] == ["ACME CORP S.L.", "Calle Mayor 1"]
    assert all(span.box is None for span in layout.spans)


@pytest.mark.parametrize(
    "content",
    [
        minimal_pdf(extra=b"2 0 obj<</Type/Page/MediaBox[0 0 595 842]>>endobj\n"),
        minimal_pdf(extra=b"2 0 obj<</Rotate 90>>endobj\n"),
        minimal_pdf(extra=b"2 0 obj<</CropBox[0 0 300 400]>>endobj\n"),
        b"%PDF-1.4\nno page tree here\n%%EOF\n",
    ],
    ids=["mixed-sizes", "rotated", "cropped", "hidden"],
)
def test_an_ambiguous_page_size_is_refused_rather_than_guessed(content: bytes):
    assert page_size_from_pdf(content) is None


def test_a_page_size_inside_a_compressed_object_stream_is_still_found():
    import zlib

    hidden = zlib.compress(b"<</Type/Page/MediaBox[0 0 612 792]>>")
    content = b"%PDF-1.5\n5 0 obj<</Type/ObjStm>>stream\n" + hidden + b"endstream endobj\n%%EOF\n"
    assert page_size_from_pdf(content) == (612.0, 792.0)
