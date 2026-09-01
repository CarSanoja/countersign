"""The one deterministic call: /build with a json-content output.

Only the Processor key is provisioned on this account, so the Data Extraction product
is unreachable and this is the path that still returns text with layout. Measured, not
assumed: /analyze_build prices this request at 3 credits for the json-content output
plus 2 more when the OCR action runs, and it answers on the Processor key even though
it bills the output as a data_extraction_api feature. Nothing here interprets the
document; it only asks for what is printed on it.
"""

import json
from pathlib import Path
from typing import Any, Final

import httpx
from autocurricula.tools.base import ToolResult

from countersign.agents.document_extractor_layout import parse_layout
from countersign.agents.document_extractor_pagesize import page_size_from_pdf
from countersign.tools import nutrient_client as client

BUILD_PATH: Final[str] = "/build"
ANALYZE_PATH: Final[str] = "/analyze_build"
PART_NAME: Final[str] = "document"
DEFAULT_OCR_LANGUAGE: Final[str] = "spanish"
ANALYZE_TIMEOUT_SECONDS: Final[float] = 30.0


def build_instructions(ocr_language: str | None = DEFAULT_OCR_LANGUAGE) -> dict[str, Any]:
    """OCR first when asked, because a scanned invoice carries no text layer and
    json-content over a document without one returns nothing rather than failing."""
    actions = (
        [{"type": "ocr", "language": ocr_language, "skipOcrForSearchableDocuments": True}]
        if ocr_language
        else []
    )
    return {
        "parts": [{"file": PART_NAME}],
        "actions": actions,
        "output": {"type": "json-content", "plainText": True, "structuredText": True},
    }


async def fetch_layout(
    document_path: str,
    *,
    ocr_language: str | None = DEFAULT_OCR_LANGUAGE,
    page_size: tuple[float, float] | None = None,
    timeout: float = client.PROCESSOR_TIMEOUT_SECONDS,
) -> ToolResult:
    """Return every text line of the document with the page region it occupies.

    Mutates external state: debits Processor credits. The page size is read from the
    file, since the response carries none, and a document whose size cannot be
    established unambiguously comes back with spans that have no box rather than with
    boxes in points pretending to be fractions.
    """
    document = await client.read_document(document_path)
    if isinstance(document, ToolResult):
        return document
    size = page_size or page_size_from_pdf(document)
    try:
        response = await client.post_document(
            BUILD_PATH,
            headers=client.processor_headers(),
            part_name=PART_NAME,
            filename=Path(document_path).name,
            content=document,
            instructions=json.dumps(build_instructions(ocr_language)),
            timeout=timeout,
        )
        body = client.response_json(response)
    except Exception as error:
        return client.failure_from(error)
    layout = parse_layout(document_path, body, page_size=size)
    return ToolResult.success(
        {
            "layout": layout.model_dump(mode="json"),
            "span_count": len(layout.spans),
            "spans_without_a_box": sum(1 for span in layout.spans if span.box is None),
            "page_size": list(size) if size else None,
            "page_size_source": _size_source(page_size, size),
            "credit_cost": response.headers.get("x-pspdfkit-request-cost"),
        }
    )


async def price_request(
    ocr_language: str | None = DEFAULT_OCR_LANGUAGE, *, timeout: float = ANALYZE_TIMEOUT_SECONDS
) -> ToolResult:
    """Validate and price the identical request without running it, for free.

    Does not mutate external state, and takes no document: /analyze_build reads the
    instructions as a JSON body and answers 415 to the multipart form /build expects.
    """
    instructions = build_instructions(ocr_language)
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(
                f"{client.BASE_URL}{ANALYZE_PATH}",
                headers=client.processor_headers(),
                json=instructions,
            )
    except httpx.HTTPError as error:
        fault = client.NutrientTransportError(f"{type(error).__name__}: {error}")
        return client.failure_from(fault)
    if response.status_code >= 400:
        return client.failure_from(client.NutrientHttpError(response.status_code, response.text))
    return ToolResult.success({"instructions": instructions, "analysis": response.json()})


def _size_source(given: tuple[float, float] | None, resolved: tuple[float, float] | None) -> str:
    if given is not None:
        return "caller"
    return "pdf-mediabox" if resolved is not None else "unknown"
