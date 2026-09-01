"""The layout of a document, and how a Nutrient json-content body becomes one.

Verified against a real /build response, because two of its properties are not what a
reader would assume. A line carries a box and an index range into the word list but no
text of its own, so a line's text has to be assembled from its words. And a page
reports no size at all, so the fraction this project's contract requires cannot come
from this response: a span whose page size is unknown keeps no box, since a box in
unknown units still looks like evidence.
"""

from collections.abc import Sequence
from typing import Any, Final

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

from countersign.schemas.evidence import PageBox

MAX_SPAN_CHARS: Final[int] = 400


class LayoutPage(StrictBaseModel):
    """One page and the size every box on it was divided by."""

    number: int
    width: float
    height: float


class LayoutSpan(StrictBaseModel):
    """One text line the parser found.

    ocr_confidence is the provider's own word score on its 0 to 100 scale, taken as
    the worst word in the line: a bank account is only as trustworthy as the least
    legible character in it.
    """

    span_id: str
    page: int
    text: str
    box: PageBox | None = None
    ocr_confidence: float | None = None


class DocumentLayout(StrictBaseModel):
    document_path: str
    pages: list[LayoutPage] = Field(default_factory=list)
    spans: list[LayoutSpan] = Field(default_factory=list)

    def span(self, span_id: str) -> LayoutSpan | None:
        return next((item for item in self.spans if item.span_id == span_id), None)


def parse_layout(
    document_path: str, body: dict[str, Any], *, page_size: tuple[float, float] | None = None
) -> DocumentLayout:
    """Read a json-content body into spans, with boxes only if the page size is known."""
    pages: list[LayoutPage] = []
    spans: list[LayoutSpan] = []
    for number, raw in enumerate(body.get("pages") or []):
        if not isinstance(raw, dict):
            continue
        if page_size is not None:
            pages.append(LayoutPage(number=number, width=page_size[0], height=page_size[1]))
        spans.extend(_page_spans(raw, number, page_size))
    return DocumentLayout(document_path=document_path, pages=pages, spans=spans)


def _page_spans(
    raw: dict[str, Any], number: int, size: tuple[float, float] | None
) -> list[LayoutSpan]:
    structured = raw.get("structuredText")
    structured = structured if isinstance(structured, dict) else {}
    words = [item for item in structured.get("words") or [] if isinstance(item, dict)]
    lines = [item for item in structured.get("lines") or [] if isinstance(item, dict)]
    spans = [
        span
        for position, line in enumerate(lines)
        if (span := _line_span(line, words, number, position, size)) is not None
    ]
    if spans:
        return spans
    return _plain_text_spans(raw.get("plainText"), number)


def _line_span(
    line: dict[str, Any],
    words: Sequence[dict[str, Any]],
    number: int,
    position: int,
    size: tuple[float, float] | None,
) -> LayoutSpan | None:
    first = _as_int(line.get("firstWordIndex"))
    count = _as_int(line.get("wordCount"))
    if first is None or count is None or first < 0 or count <= 0:
        return None
    chosen = words[first : first + count]
    text = " ".join(value for word in chosen if (value := _word_text(word)))
    if not text:
        return None
    return LayoutSpan(
        span_id=f"p{number}l{position}",
        page=number,
        text=text[:MAX_SPAN_CHARS],
        box=_page_box(line.get("bbox"), number, size),
        ocr_confidence=_worst_confidence(chosen),
    )


def _plain_text_spans(plain: Any, number: int) -> list[LayoutSpan]:
    """The last resort: text with no geometry at all, so page-level provenance only."""
    if not isinstance(plain, str):
        return []
    return [
        LayoutSpan(span_id=f"p{number}t{position}", page=number, text=text[:MAX_SPAN_CHARS])
        for position, line in enumerate(plain.splitlines())
        if (text := line.strip())
    ]


def _word_text(word: dict[str, Any]) -> str:
    value = word.get("value")
    return value.strip() if isinstance(value, str) else ""


def _worst_confidence(words: Sequence[dict[str, Any]]) -> float | None:
    scores = [score for word in words if (score := _as_float(word.get("confidence"))) is not None]
    return min(scores) if scores else None


def _page_box(raw: Any, number: int, size: tuple[float, float] | None) -> PageBox | None:
    if size is None or not isinstance(raw, dict):
        return None
    left = _as_float(raw.get("left"))
    top = _as_float(raw.get("top"))
    width = _as_float(raw.get("width"))
    height = _as_float(raw.get("height"))
    if left is None or top is None or width is None or height is None:
        return None
    page_width, page_height = size
    return PageBox(
        page=number,
        left=_fraction(left, page_width),
        top=_fraction(top, page_height),
        width=_fraction(width, page_width),
        height=_fraction(height, page_height),
    )


def _fraction(value: float, total: float) -> float:
    """Clamped: losing a whole citation to a box that overhangs by a rounding error
    helps nobody, and the origin is the top left corner, as the Processor reports it."""
    return min(1.0, max(0.0, value / total)) if total > 0 else 0.0


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return None if number is None else int(number)
