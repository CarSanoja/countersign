"""The claim under test: a value the document does not carry comes back absent."""

import json

from document_extractor_fixtures import (
    FAITHFUL_ANSWER,
    PAGE_SIZE,
    FakeModel,
    json_content_body,
)

from countersign.agents.document_extractor import ExtractedInvoice, extract_from_layout
from countersign.agents.document_extractor_layout import parse_layout
from countersign.agents.document_extractor_model import TextModel
from countersign.schemas.evidence import Provider

DOCUMENT = "/tmp/acme-invoice.pdf"


def layout(body=None):
    return parse_layout(DOCUMENT, body or json_content_body(), page_size=PAGE_SIZE)


async def invoice_from(answer: str, body=None) -> ExtractedInvoice:
    result = await extract_from_layout(layout(body), FakeModel(answer))
    assert result.ok, result.error
    return ExtractedInvoice.model_validate(result.payload["invoice"])


def test_the_fake_satisfies_the_injected_model_contract():
    assert isinstance(FakeModel(""), TextModel)


async def test_every_anchored_field_carries_the_region_it_was_read_from():
    invoice = await invoice_from(FAITHFUL_ANSWER)
    assert invoice.legal_name is not None
    assert invoice.legal_name.source.provider == Provider.NUTRIENT
    assert invoice.legal_name.source.locator == DOCUMENT
    box = invoice.legal_name.source.box
    assert box is not None
    assert box.page == 0
    assert round(box.left, 4) == round(72 / 612, 4)
    assert round(box.top, 4) == round(64.08 / 792, 4)
    assert 0.0 < box.width < 1.0


async def test_a_reformatted_iban_still_anchors_to_the_span_that_prints_it():
    invoice = await invoice_from(FAITHFUL_ANSWER)
    assert invoice.iban is not None
    assert invoice.iban.value == "ES9121000418450200051332"
    assert "ES91 2100" in invoice.iban.source.snippet


async def test_two_fields_can_come_from_the_same_line():
    invoice = await invoice_from(FAITHFUL_ANSWER)
    assert invoice.invoice_number is not None
    assert invoice.total_amount is not None
    assert invoice.invoice_number.span_id == invoice.total_amount.span_id == "p0l4"


async def test_an_invented_value_is_absent_and_recorded_rather_than_returned():
    answer = json.dumps(
        {"fields": [{"field": "iban", "span_id": "p0l2", "value": "DE89370400440532013000"}]}
    )
    invoice = await invoice_from(answer)
    assert invoice.iban is None
    assert "iban" in invoice.missing_fields
    assert [item.claimed_value for item in invoice.dropped] == ["DE89370400440532013000"]


async def test_a_citation_to_a_span_that_does_not_exist_is_refused():
    answer = json.dumps(
        {"fields": [{"field": "legal_name", "span_id": "p9l9", "value": "ACME CORP S.L."}]}
    )
    invoice = await invoice_from(answer)
    assert invoice.legal_name is None
    assert "is not in this document" in invoice.dropped[0].reason


async def test_a_domain_is_anchored_as_a_host_name_not_as_a_substring():
    body = json_content_body()
    words = body["pages"][0]["structuredText"]["words"]
    words[-2]["value"] = "billing@acmecorp.com-invoices.net"
    words[-1]["value"] = "www.acmecorp.com-invoices.net"
    answer = json.dumps(
        {"fields": [{"field": "sender_domain", "span_id": "p0l5", "value": "acmecorp.com"}]}
    )
    invoice = await invoice_from(answer, body)
    assert invoice.sender_domain is None
    assert invoice.dropped[0].reason.endswith("does not carry this value")


async def test_the_sender_domain_is_reduced_to_a_bare_host_name():
    answer = json.dumps(
        {"fields": [{"field": "sender_domain", "span_id": "p0l5", "value": "www.acmecorp.com"}]}
    )
    invoice = await invoice_from(answer)
    assert invoice.sender_domain is not None
    assert invoice.sender_domain.value == "acmecorp.com"


async def test_a_field_mapped_twice_keeps_the_first_and_records_the_second():
    answer = json.dumps(
        {
            "fields": [
                {"field": "invoice_number", "span_id": "p0l4", "value": "F-2026-118"},
                {"field": "invoice_number", "span_id": "p0l4", "value": "12.480,00"},
            ]
        }
    )
    invoice = await invoice_from(answer)
    assert invoice.invoice_number is not None
    assert invoice.invoice_number.value == "F-2026-118"
    assert invoice.dropped[0].reason.startswith("mapped twice")


async def test_a_claim_never_outranks_the_confidence_of_the_reading():
    invoice = await invoice_from(FAITHFUL_ANSWER)
    assert invoice.iban is not None and invoice.iban.ocr_confidence is not None
    claims = invoice.claims()
    assert len(claims) == len(invoice.present_fields)
    iban_claim = next(claim for claim in claims if "iban" in claim.statement)
    assert iban_claim.confidence == invoice.iban.ocr_confidence / 100.0
    assert all(claim.sources for claim in claims)


async def test_the_prompt_offers_spans_and_never_the_document():
    model = FakeModel(FAITHFUL_ANSWER)
    await extract_from_layout(layout(), model)
    prompt = model.prompts[0]
    assert "[p0l2] IBAN: ES91 2100 0418 4502 0005 1332" in prompt
    assert DOCUMENT not in prompt
