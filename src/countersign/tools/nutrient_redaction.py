"""Permanent removal of PII from a supplier document. Capability: doc.extract.

Redaction on this API is two steps whose defaults contradict each other between
endpoints, so the sequence is spelled out here rather than left to a shortcut:
/build is the only surface that can run OCR before the patterns are matched.
"""

import json
from pathlib import Path
from typing import Any, Final

from autocurricula.tools.base import ToolResult, as_function_tool

from countersign.tools import nutrient_client as client

REDACTION_PRESETS: Final[frozenset[str]] = frozenset(
    {
        "credit-card-number", "date", "email-address", "international-phone-number",
        "ipv4", "ipv6", "mac-address", "north-american-phone-number",
        "social-security-number", "time", "url", "us-zip-code", "vin",
    }
)
DEFAULT_PII_PRESETS: Final[tuple[str, ...]] = (
    "email-address",
    "international-phone-number",
    "credit-card-number",
    "social-security-number",
)
FREE_PLAN_WATERMARK_NOTE: Final[str] = (
    "The Processor free plan stamps 'For Evaluation Purposes Only' on every output and "
    "only a paid plan removes it. Inspect the returned PDF before putting it in front "
    "of a reviewer."
)


async def nutrient_redact_pii(
    document_path: str,
    output_path: str,
    ocr_language: str = "spanish",
    presets: list[str] | None = None,
    regex_patterns: list[str] | None = None,
) -> ToolResult:
    """OCR the document, mark PII and erase it, in that order, in one call.

    Mutates external state: debits Processor credits and writes a PDF whose
    redacted content is gone for good. OCR runs first because a scan carries no
    text layer and pattern redaction over a document without one silently
    matches nothing; applyRedactions runs last because createRedactions only
    draws a box over text that stays extractable underneath it.
    """
    chosen = tuple(presets) if presets is not None else DEFAULT_PII_PRESETS
    unknown = sorted(set(chosen) - REDACTION_PRESETS)
    if unknown:
        return ToolResult.failure(f"unknown redaction presets {unknown}")
    document = await client.read_document(document_path)
    if isinstance(document, ToolResult):
        return document
    patterns = tuple(regex_patterns or ())
    instructions = {
        "parts": [{"file": "document"}],
        "actions": _redaction_actions(ocr_language, chosen, patterns),
        "output": {"type": "pdf"},
    }
    try:
        response = await client.post_document(
            "/build",
            headers=client.processor_headers(),
            part_name="document",
            filename=Path(document_path).name,
            content=document,
            instructions=json.dumps(instructions),
            timeout=client.PROCESSOR_TIMEOUT_SECONDS,
        )
        await client.write_document(output_path, response.content)
    except Exception as error:
        return client.failure_from(error)
    return ToolResult.success(
        {
            "output_path": output_path,
            "presets_applied": list(chosen),
            "regex_patterns_applied": list(patterns),
            "ocr_language": ocr_language,
            "credit_cost": response.headers.get("x-pspdfkit-request-cost"),
            "watermark_warning": FREE_PLAN_WATERMARK_NOTE,
        }
    )


def _redaction_actions(
    ocr_language: str, presets: tuple[str, ...], patterns: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Order is execution order: recognise, then mark, then erase."""
    actions: list[dict[str, Any]] = [
        {"type": "ocr", "language": ocr_language, "skipOcrForSearchableDocuments": True}
    ]
    actions += [
        {"type": "createRedactions", "strategy": "preset", "strategyOptions": {"preset": preset}}
        for preset in presets
    ]
    actions += [
        {
            "type": "createRedactions",
            "strategy": "regex",
            "strategyOptions": {"regex": pattern, "caseSensitive": False},
        }
        for pattern in patterns
    ]
    actions.append({"type": "applyRedactions"})
    return actions


redact_pii_tool = as_function_tool(nutrient_redact_pii)
