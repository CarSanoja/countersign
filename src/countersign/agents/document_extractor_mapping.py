"""The single model call. Its whole job is to point, not to read.

The spans below were produced deterministically by Nutrient. The model never sees the
PDF, so it cannot read a value that is not already in a span, and the span id it cites
is what the next step checks the value against.
"""

from collections.abc import Sequence
from typing import Any, Final

from autocurricula.agents.base import parse_model_json
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.tools.base import ToolResult
from pydantic import Field

from countersign.agents.document_extractor_fields import FIELD_GUIDANCE, InvoiceField
from countersign.agents.document_extractor_layout import LayoutSpan
from countersign.agents.document_extractor_model import TextModel
from countersign.agents.pii_mask import mask_pii

MAPPER_MODEL: Final[str] = "gemini-3.5-flash-lite"
MAX_PROMPT_SPANS: Final[int] = 400

TASK: Final[str] = """You are mapping a supplier document that has already been parsed.
Below is every text span a deterministic PDF parser found, each with its span id.

You are a mapper, not a reader. The only values that exist are the ones printed in
these spans.

Rules:
- Cite a span id from the list. Any other id is a failure.
- Copy the value character for character out of the span you cite. Do not reformat,
  translate, complete, convert or compute anything.
- If no span carries a field, leave that field out. An omitted field is a correct
  answer; an invented one is not, and will be discarded anyway.
- At most one entry per field.

Fields to look for:
{fields}

Spans:
{spans}

Answer with JSON only, in this shape:
{{"fields": [{{"field": "invoice_number", "span_id": "p0s4", "value": "F-2026-118"}}]}}"""


class SpanMapping(StrictBaseModel):
    """One field the model claims a span carries. Still a claim, not yet a fact."""

    field: InvoiceField
    span_id: str = Field(min_length=1)
    value: str = Field(min_length=1)


def build_prompt(spans: Sequence[LayoutSpan]) -> str:
    field_lines = "\n".join(f"- {name.value}: {text}" for name, text in FIELD_GUIDANCE.items())
    span_lines = "\n".join(
        f"[{span.span_id}] {mask_pii(span.text)}" for span in spans[:MAX_PROMPT_SPANS]
    )
    return TASK.format(fields=field_lines, spans=span_lines)


async def map_spans_to_fields(
    spans: Sequence[LayoutSpan], model: TextModel, *, model_name: str = MAPPER_MODEL
) -> ToolResult:
    """Ask the model which span holds which field. Does not mutate external state."""
    if not spans:
        return ToolResult.failure("no spans to map: the document produced no text")
    try:
        raw = await model.generate_text(build_prompt(spans), model=model_name)
    except Exception as error:
        return ToolResult.failure(f"model call failed: {type(error).__name__}: {error}")
    try:
        payload = parse_model_json(raw)
    except ValueError as error:
        return ToolResult.failure(f"model answer was not JSON: {error}")
    mappings, rejected = read_mappings(payload)
    return ToolResult.success(
        {
            "mappings": [mapping.model_dump(mode="json") for mapping in mappings],
            "rejected": rejected,
            "model": model_name,
            "spans_offered": min(len(spans), MAX_PROMPT_SPANS),
        }
    )


def read_mappings(payload: Any) -> tuple[list[SpanMapping], list[str]]:
    """Keep the entries that are well formed and say why the others were dropped."""
    entries = payload.get("fields") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return [], ["model answer had no 'fields' list"]
    mappings: list[SpanMapping] = []
    rejected: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            rejected.append(f"entry is not an object: {entry!r}")
            continue
        try:
            mappings.append(
                SpanMapping(
                    field=InvoiceField(str(entry.get("field", ""))),
                    span_id=str(entry.get("span_id", "")),
                    value=str(entry.get("value", "")),
                )
            )
        except ValueError:
            rejected.append(f"unusable entry: {entry!r}")
    return mappings, rejected
