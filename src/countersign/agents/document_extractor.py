"""Fleet agent 2: extraction that a person can check line by line.

Nutrient returns the text and the layout deterministically. The model does one thing
with that: it maps spans that already exist onto named fields. Every value it proposes
is then checked back against the span it cited, and a value the span does not carry is
returned as absent instead of as a field. That gap between an anchored value and a
plausible one is the whole point of the agent.
"""

from collections.abc import Sequence
from typing import Final

from autocurricula.schemas.common import StrictBaseModel, utc_now
from autocurricula.tools.base import ToolResult
from pydantic import Field

from countersign.agents.document_extractor_fields import InvoiceField, anchor_value
from countersign.agents.document_extractor_layout import DocumentLayout, LayoutSpan
from countersign.agents.document_extractor_mapping import (
    MAPPER_MODEL,
    SpanMapping,
    map_spans_to_fields,
)
from countersign.agents.document_extractor_model import TextModel
from countersign.agents.document_extractor_nutrient import DEFAULT_OCR_LANGUAGE, fetch_layout
from countersign.schemas.evidence import Claim, Provider, SourceRef

ANCHORED_CONFIDENCE: Final[float] = 0.9
"""Not 1.0. The value is provably printed in the cited span, which is checked, but the
field it was mapped to is still the model's judgement, which is not."""


class DroppedField(StrictBaseModel):
    """A field the model proposed and the anchor check refused.

    Kept, rather than silently discarded: a proposal that no span supports is the most
    interesting line in an audit of the extraction.
    """

    field: str
    claimed_value: str
    reason: str


class ExtractedField(StrictBaseModel):
    """A value together with the exact region of the document it was read from.

    ocr_confidence is the parser's own score for the worst word in that region, on its
    0 to 100 scale, and is absent when the parser reported none.
    """

    value: str
    span_id: str
    source: SourceRef
    ocr_confidence: float | None = None


class ExtractedInvoice(StrictBaseModel):
    """What the document says, restricted to what it demonstrably says."""

    document_path: str
    extracted_at: str = Field(min_length=1)
    page_count: int = 0
    legal_name: ExtractedField | None = None
    address: ExtractedField | None = None
    iban: ExtractedField | None = None
    account_number: ExtractedField | None = None
    routing_number: ExtractedField | None = None
    total_amount: ExtractedField | None = None
    invoice_number: ExtractedField | None = None
    sender_domain: ExtractedField | None = None
    dropped: list[DroppedField] = Field(default_factory=list)

    def field(self, name: InvoiceField) -> ExtractedField | None:
        value = getattr(self, name.value)
        return value if isinstance(value, ExtractedField) else None

    @property
    def present_fields(self) -> list[str]:
        return [name.value for name in InvoiceField if self.field(name) is not None]

    @property
    def missing_fields(self) -> list[str]:
        return [name.value for name in InvoiceField if self.field(name) is None]

    def claims(self) -> list[Claim]:
        """Each anchored field as a claim the risk synthesiser can carry forward."""
        return [
            Claim(
                statement=f"the document states {name.value.replace('_', ' ')} "
                f"= {extracted.value}",
                sources=[extracted.source],
                confidence=_confidence(extracted),
            )
            for name in InvoiceField
            if (extracted := self.field(name)) is not None
        ]


async def extract_invoice(
    document_path: str,
    model: TextModel,
    *,
    model_name: str = MAPPER_MODEL,
    ocr_language: str | None = DEFAULT_OCR_LANGUAGE,
    page_size: tuple[float, float] | None = None,
) -> ToolResult:
    """Parse the document with Nutrient, then map its spans onto named fields.

    Mutates external state: the Nutrient /build call debits Processor credits.
    """
    parsed = await fetch_layout(document_path, ocr_language=ocr_language, page_size=page_size)
    if not parsed.ok:
        return parsed
    layout = DocumentLayout.model_validate(parsed.payload["layout"])
    return await extract_from_layout(layout, model, model_name=model_name)


async def extract_from_layout(
    layout: DocumentLayout, model: TextModel, *, model_name: str = MAPPER_MODEL
) -> ToolResult:
    """The half that needs no network beyond the model, and no credentials to test."""
    if not layout.spans:
        return ToolResult.failure(
            f"nutrient returned no text for {layout.document_path}; "
            "a scan with no OCR result cannot be extracted from"
        )
    mapped = await map_spans_to_fields(layout.spans, model, model_name=model_name)
    if not mapped.ok:
        return mapped
    mappings = [SpanMapping.model_validate(entry) for entry in mapped.payload["mappings"]]
    invoice = assemble(layout, mappings)
    return ToolResult.success(
        {
            "invoice": invoice.model_dump(mode="json"),
            "present_fields": invoice.present_fields,
            "missing_fields": invoice.missing_fields,
            "dropped_fields": [item.field for item in invoice.dropped],
            "rejected_entries": mapped.payload["rejected"],
            "spans_considered": len(layout.spans),
            "model": model_name,
        }
    )


def assemble(
    layout: DocumentLayout, mappings: Sequence[SpanMapping], *, retrieved_at: str | None = None
) -> ExtractedInvoice:
    """Turn proposals into fields, keeping only the ones their own span supports."""
    stamp = retrieved_at or utc_now().isoformat()
    anchored: dict[str, ExtractedField] = {}
    dropped: list[DroppedField] = []
    for mapping in mappings:
        name = mapping.field.value
        if name in anchored:
            dropped.append(_dropped(mapping, "mapped twice; the first anchored mapping stands"))
            continue
        span = layout.span(mapping.span_id)
        if span is None:
            dropped.append(_dropped(mapping, f"span {mapping.span_id} is not in this document"))
            continue
        value = anchor_value(mapping.field, mapping.value, span.text)
        if value is None:
            dropped.append(_dropped(mapping, f"span {span.span_id} does not carry this value"))
            continue
        anchored[name] = ExtractedField(
            value=value,
            span_id=span.span_id,
            source=_source(layout, span, stamp),
            ocr_confidence=span.ocr_confidence,
        )
    return ExtractedInvoice(
        document_path=layout.document_path,
        extracted_at=stamp,
        page_count=len({span.page for span in layout.spans}) or len(layout.pages),
        dropped=dropped,
        **anchored,
    )


def _confidence(extracted: ExtractedField) -> float:
    """Never claim more confidence in a value than the parser had in reading it."""
    if extracted.ocr_confidence is None:
        return ANCHORED_CONFIDENCE
    return min(ANCHORED_CONFIDENCE, max(0.0, extracted.ocr_confidence) / 100.0)


def _dropped(mapping: SpanMapping, reason: str) -> DroppedField:
    return DroppedField(field=mapping.field.value, claimed_value=mapping.value, reason=reason)


def _source(layout: DocumentLayout, span: LayoutSpan, stamp: str) -> SourceRef:
    return SourceRef(
        provider=Provider.NUTRIENT,
        locator=layout.document_path,
        box=span.box,
        snippet=span.text,
        retrieved_at=stamp,
    )
