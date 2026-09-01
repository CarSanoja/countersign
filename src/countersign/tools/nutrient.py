"""Nutrient DWS tools for COUNTERSIGN. Capability required: doc.extract.

The tool surface the fleet is allowed to reach: pull typed fields out of a
supplier document with the page and box each value came from, and permanently
remove PII from that document before its text reaches a model. Signing is a
Nutrient product too and is deliberately absent, because no agent in this fleet
holds signature.execute and nothing here should be able to reach /sign.
"""

import json
from pathlib import Path
from typing import Any, Final

from autocurricula.tools.base import ToolResult, as_function_tool

from countersign.tools import nutrient_client as client
from countersign.tools.nutrient_redaction import nutrient_redact_pii, redact_pii_tool
from countersign.tools.nutrient_schemas import (
    PARSE_MODES,
    provenance_from_metadata,
    validate_extraction_schema,
)

__all__ = [
    "extract_fields_tool",
    "nutrient_credit_balance",
    "nutrient_extract_fields",
    "nutrient_redact_pii",
    "redact_pii_tool",
]

ACCOUNT_PRODUCTS: Final[frozenset[str]] = frozenset(
    {"processor", "viewer", "signing_workflow", "accessibility", "data_extraction"}
)


async def nutrient_extract_fields(
    document_path: str,
    field_schema: dict[str, Any],
    guidance: str = "",
    parse_mode: str = "structure",
) -> ToolResult:
    """Map a document onto a caller-supplied JSON Schema and return every value
    together with the page regions it was read from.

    Mutates external state: debits Data Extraction credits, 7.5 per page in
    'structure' and 15 in 'understand'. Nothing is kept server side, since
    storeRun stays false and a document carrying PII leaves no copy behind.
    """
    if parse_mode not in PARSE_MODES:
        return ToolResult.failure(f"parse_mode must be one of {sorted(PARSE_MODES)}")
    problems = validate_extraction_schema(field_schema)
    if problems:
        return ToolResult.failure("extraction schema rejected locally: " + "; ".join(problems))
    document = await client.read_document(document_path)
    if isinstance(document, ToolResult):
        return document
    instructions: dict[str, Any] = {
        "schema": field_schema,
        "parseConfig": {"mode": parse_mode, "options": {"language": "auto"}},
        "options": {"includeCitations": True, "strict": True},
        "storeRun": False,
    }
    if guidance:
        instructions["instructions"] = guidance
    try:
        response = await client.post_document(
            "/extraction/extract",
            headers=client.extraction_headers(),
            part_name="file",
            filename=Path(document_path).name,
            content=document,
            instructions=json.dumps(instructions),
            timeout=client.EXTRACTION_TIMEOUT_SECONDS,
        )
        body = client.response_json(response)
    except Exception as error:
        return client.failure_from(error)
    return ToolResult.success(_extraction_payload(body, parse_mode))


def _extraction_payload(body: dict[str, Any], parse_mode: str) -> dict[str, Any]:
    """Review is routed by `match`, never by a confidence threshold: the score is
    uncalibrated and its absence means no score exists, not low confidence."""
    output = body.get("output") or {}
    pages = output.get("pages") or []
    provenance = provenance_from_metadata(output.get("metadata") or {}, pages)
    credits = (body.get("usage") or {}).get("data_extraction_credits") or {}
    return {
        "fields": output.get("data") or {},
        "provenance": [record.model_dump(mode="json") for record in provenance],
        "pages": pages,
        "needs_review": [record.field_path for record in provenance if record.needs_review],
        "parse_mode": parse_mode,
        "request_id": body.get("requestId"),
        "credits_spent": credits.get("cost"),
        "credits_remaining": credits.get("remainingCredits"),
    }


async def nutrient_credit_balance(product: str = "data_extraction") -> ToolResult:
    """Read subscription state and credit consumption for one product. Does not
    mutate external state.

    Unverified: which of the two keys /account/{product}/usage expects. The key
    is picked by product here, extraction key for data_extraction and processor
    key otherwise, and that routing has never been exercised against the API.
    """
    if product not in ACCOUNT_PRODUCTS:
        return ToolResult.failure(f"product must be one of {sorted(ACCOUNT_PRODUCTS)}")
    try:
        headers = (
            client.extraction_headers()
            if product == "data_extraction"
            else client.processor_headers()
        )
        response = await client.get_json(
            f"/account/{product}/usage",
            headers=headers,
            timeout=client.ACCOUNT_TIMEOUT_SECONDS,
        )
        body = client.response_json(response)
    except Exception as error:
        return client.failure_from(error)
    return ToolResult.success({"product": product, "account": body})


def nutrient_redaction_appearance(**options: Any) -> dict[str, Any]:
    """Build the visual appearance of a redaction box. Not implemented."""
    raise NotImplementedError(
        "The RedactionAnnotation model behind createRedactions.content was never "
        "resolved out of the OpenAPI document, so the property names for background "
        "colour and overlay text are unknown. Read the RedactionAnnotation schema in "
        "the Processor spec public@1.18.0.yml before writing this."
    )


def nutrient_async_redaction_job(**options: Any) -> dict[str, Any]:
    """Submit /build with Prefer: respond-async and poll it. Not implemented."""
    raise NotImplementedError(
        "Async build needs the job_access_token ('jat_' prefix) returned in the 202 "
        "admission body, replayed as the X-Async-Job-Token header on every poll, and "
        "the spec refuses async work for trial accounts with 403 "
        "unsupported_async_request_kind. Neither the plan tier behind the hackathon "
        "campaign key nor a real 202 body has been observed."
    )


extract_fields_tool = as_function_tool(nutrient_extract_fields)
