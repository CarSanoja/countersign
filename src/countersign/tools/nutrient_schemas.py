"""Contract types for the Nutrient extraction surface.

Boxes are normalised to a fraction of the page. The two Nutrient APIs report
coordinates in different units and the render DPI is undocumented, so the page
size returned alongside a box is the only stable reference there is.
"""

import json
from typing import Any

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

ALLOWED_SCHEMA_KEYWORDS = frozenset(
    {"type", "properties", "required", "items", "description", "enum", "format"}
)
MAX_SCHEMA_BYTES = 32_768
MAX_SCHEMA_FIELDS = 500
MAX_OBJECT_PROPERTIES = 50
MAX_SCHEMA_DEPTH = 5
MAX_ENUM_VALUES = 50
MAX_ENUM_VALUE_CHARS = 256
MAX_DESCRIPTION_CHARS = 1_024
MAX_PROPERTY_NAME_CHARS = 128

REVIEW_MATCHES = frozenset({"fuzzy_match", "not_found"})
PARSE_MODES = frozenset({"structure", "understand", "agentic"})


class PageBox(StrictBaseModel):
    """One source region, as a fraction of its page rather than in device units."""

    page_number: int
    left: float
    top: float
    width: float
    height: float


class FieldProvenance(StrictBaseModel):
    """Where one extracted value came from, and whether a person should look."""

    field_path: str
    match: str
    confidence: float | None = None
    recognition_score: float | None = None
    needs_review: bool
    boxes: list[PageBox] = Field(default_factory=list)


def validate_extraction_schema(schema: dict[str, Any]) -> list[str]:
    """Report what /extraction/extract would reject, before spending a request.

    The accepted JSON Schema is a closed subset, so a schema exported from
    pydantic or zod almost always fails on the $defs and $ref it emits.
    """
    problems: list[str] = []
    if len(json.dumps(schema, default=str).encode()) > MAX_SCHEMA_BYTES:
        problems.append(f"schema exceeds {MAX_SCHEMA_BYTES} bytes serialised")
    if schema.get("type") != "object":
        problems.append("root schema must declare type 'object'")
    total = _inspect(schema, "$", 1, problems)
    if total > MAX_SCHEMA_FIELDS:
        problems.append(f"schema declares {total} fields, over the {MAX_SCHEMA_FIELDS} limit")
    return problems


def _inspect(node: dict[str, Any], path: str, depth: int, problems: list[str]) -> int:
    if depth > MAX_SCHEMA_DEPTH:
        problems.append(f"{path} nests deeper than {MAX_SCHEMA_DEPTH} levels")
        return 0
    unsupported = sorted(set(node) - ALLOWED_SCHEMA_KEYWORDS)
    if unsupported:
        problems.append(f"{path} uses unsupported keywords {unsupported}")
    _inspect_leaf_limits(node, path, problems)
    properties = node.get("properties") or {}
    if len(properties) > MAX_OBJECT_PROPERTIES:
        problems.append(f"{path} declares more than {MAX_OBJECT_PROPERTIES} properties")
    count = 0
    for name, child in properties.items():
        if len(name) > MAX_PROPERTY_NAME_CHARS:
            problems.append(f"{path}.{name} exceeds {MAX_PROPERTY_NAME_CHARS} characters")
        count += 1
        if isinstance(child, dict):
            count += _inspect(child, f"{path}.{name}", depth + 1, problems)
    items = node.get("items")
    if isinstance(items, dict):
        count += _inspect(items, f"{path}[]", depth + 1, problems)
    return count


def _inspect_leaf_limits(node: dict[str, Any], path: str, problems: list[str]) -> None:
    declared_format = node.get("format")
    if declared_format is not None and declared_format != "date":
        problems.append(f"{path} uses format '{declared_format}'; only 'date' is accepted")
    description = node.get("description")
    if isinstance(description, str) and len(description) > MAX_DESCRIPTION_CHARS:
        problems.append(f"{path} description exceeds {MAX_DESCRIPTION_CHARS} characters")
    values = node.get("enum")
    if values is None:
        return
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        problems.append(f"{path} enum accepts strings only")
        return
    if len(values) > MAX_ENUM_VALUES:
        problems.append(f"{path} enum holds more than {MAX_ENUM_VALUES} values")
    if any(len(value) > MAX_ENUM_VALUE_CHARS for value in values):
        problems.append(f"{path} enum value exceeds {MAX_ENUM_VALUE_CHARS} characters")


def provenance_from_metadata(
    metadata: dict[str, Any], pages: list[dict[str, Any]]
) -> list[FieldProvenance]:
    """Flatten the citation tree into one record per extracted leaf."""
    sizes = {
        int(page.get("page", 0)): (
            _as_float(page.get("width")) or 1.0,
            _as_float(page.get("height")) or 1.0,
        )
        for page in pages
        if isinstance(page, dict)
    }
    collected: list[FieldProvenance] = []
    _collect(metadata, "", sizes, collected)
    return collected


def _collect(
    node: Any, path: str, sizes: dict[int, tuple[float, float]], collected: list[FieldProvenance]
) -> None:
    if isinstance(node, dict) and "match" in node:
        collected.append(_provenance(node, path or "$", sizes))
        return
    if isinstance(node, dict):
        for key, child in node.items():
            _collect(child, f"{path}.{key}" if path else str(key), sizes, collected)
        return
    if isinstance(node, list):
        for index, child in enumerate(node):
            _collect(child, f"{path}[{index}]", sizes, collected)


def _provenance(
    citation: dict[str, Any], path: str, sizes: dict[int, tuple[float, float]]
) -> FieldProvenance:
    match = str(citation.get("match", "not_found"))
    sources = citation.get("source_bboxes")
    regions = [source for source in sources or [] if isinstance(source, dict)]
    if not regions and isinstance(citation.get("bbox"), dict):
        regions = [citation]
    return FieldProvenance(
        field_path=path,
        match=match,
        confidence=_as_float(citation.get("confidence")),
        recognition_score=_as_float(citation.get("recognitionScore")),
        needs_review=match in REVIEW_MATCHES,
        boxes=[_page_box(region, sizes) for region in regions],
    )


def _page_box(region: dict[str, Any], sizes: dict[int, tuple[float, float]]) -> PageBox:
    box = region.get("bbox") or {}
    page_number = int(region.get("pageNumber", 1))
    width, height = sizes.get(page_number, (1.0, 1.0))
    return PageBox(
        page_number=page_number,
        left=(_as_float(box.get("x")) or 0.0) / width,
        top=(_as_float(box.get("y")) or 0.0) / height,
        width=(_as_float(box.get("width")) or 0.0) / width,
        height=(_as_float(box.get("height")) or 0.0) / height,
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
