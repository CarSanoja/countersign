"""A real /build response, kept verbatim, and a fake model.

document_extractor_response.json is what api.nutrient.io actually returned for a
one-page invoice: lines that carry a box and an index range but no text of their own,
words that carry the text, and no page size anywhere. The odd glyphs in it ('$ pain',
'SWIFTAIC') come from the hand-made PDF that was sent, not from the API, and they are
left in because a parser that only works on clean input is not a parser.
"""

import json
from pathlib import Path
from typing import Any

PAGE_SIZE = (612.0, 792.0)
RESPONSE_PATH = Path(__file__).parent / "document_extractor_response.json"


def json_content_body() -> dict[str, Any]:
    return json.loads(RESPONSE_PATH.read_text())


FAITHFUL_ANSWER = json.dumps(
    {
        "fields": [
            {"field": "legal_name", "span_id": "p0l0", "value": "ACME CORP S.L."},
            {"field": "address", "span_id": "p0l1", "value": "Calle Mayor 1, 28013 Madrid"},
            {"field": "iban", "span_id": "p0l2", "value": "ES9121000418450200051332"},
            {"field": "routing_number", "span_id": "p0l3", "value": "CAIXESBBXXX"},
            {"field": "invoice_number", "span_id": "p0l4", "value": "F-2026-118"},
            {"field": "total_amount", "span_id": "p0l4", "value": "12.480,00 EUR"},
            {"field": "sender_domain", "span_id": "p0l5", "value": "acmecorp.com"},
        ]
    }
)


class FakeModel:
    """Answers with whatever the test decided, and records what it was asked."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    async def generate_text(self, prompt: str, *, model: str) -> str:
        self.prompts.append(prompt)
        return self.answer


def minimal_pdf(media_box: str = "[0 0 612 792]", extra: bytes = b"") -> bytes:
    """The smallest file the page-size reader should still understand."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Page/MediaBox" + media_box.encode() + b">>endobj\n"
        + extra
        + b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
