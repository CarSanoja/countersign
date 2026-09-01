"""Defensive readers over a SerpApi document. Nothing here trusts a key to exist.

Two shape traps are handled on purpose: local_results is an object keyed
'places' under engine=google but a flat array under google_maps, and the
place type comes back as a string in a maps search and as an array in a
place result.
"""

from typing import Any

from countersign.tools.serpapi_models import (
    KnowledgeGraphSummary,
    NewsItem,
    OrganicResult,
    PlaceRecord,
)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _dicts(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, dict)]


def search_id(document: dict[str, Any]) -> str | None:
    metadata = document.get("search_metadata")
    return _text(metadata.get("id")) if isinstance(metadata, dict) else None


def organic_results(document: dict[str, Any], limit: int) -> list[OrganicResult]:
    return [
        OrganicResult(
            position=_int(item.get("position")),
            title=_text(item.get("title")),
            link=_text(item.get("link")),
            displayed_link=_text(item.get("displayed_link")),
            snippet=_text(item.get("snippet")),
            source=_text(item.get("source")),
        )
        for item in _dicts(document.get("organic_results"), limit)
    ]


def knowledge_graph(document: dict[str, Any]) -> KnowledgeGraphSummary | None:
    raw = document.get("knowledge_graph")
    if not isinstance(raw, dict):
        return None
    return KnowledgeGraphSummary(
        title=_text(raw.get("title")),
        website=_text(raw.get("website")),
        entity_type=_text(raw.get("type")),
        description=_text(raw.get("description")),
    )


def news_items(document: dict[str, Any], limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    for item in _dicts(document.get("news_results"), limit):
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        raw_authors = source.get("authors")
        items.append(
            NewsItem(
                position=_int(item.get("position")),
                title=_text(item.get("title")),
                link=_text(item.get("link")),
                source_name=_text(source.get("name")),
                authors=[a for a in raw_authors if isinstance(a, str)]
                if isinstance(raw_authors, list)
                else [],
                iso_date=_text(item.get("iso_date")),
            )
        )
    return items


def _place_type(value: Any) -> str | None:
    if isinstance(value, list):
        return next((_text(entry) for entry in value if _text(entry)), None)
    return _text(value)


def _place(item: dict[str, Any]) -> PlaceRecord:
    coordinates = item.get("gps_coordinates")
    coordinates = coordinates if isinstance(coordinates, dict) else {}
    return PlaceRecord(
        position=_int(item.get("position")),
        title=_text(item.get("title")),
        maps_place_id=_text(item.get("place_id")),
        data_cid=_text(item.get("data_cid")),
        address=_text(item.get("address")),
        phone=_text(item.get("phone")),
        website=_text(item.get("website")),
        rating=_float(item.get("rating")),
        reviews=_int(item.get("reviews")),
        place_type=_place_type(item.get("type")),
        open_state=_text(item.get("open_state")),
        latitude=_float(coordinates.get("latitude")),
        longitude=_float(coordinates.get("longitude")),
    )


def places(document: dict[str, Any], limit: int) -> list[PlaceRecord]:
    """Read local_results from a google_maps document, where it is a flat array."""
    raw = document.get("local_results")
    if isinstance(raw, dict):
        raw = raw.get("places")
    return [_place(item) for item in _dicts(raw, limit)]


def place_details(document: dict[str, Any]) -> PlaceRecord | None:
    raw = document.get("place_results")
    return _place(raw) if isinstance(raw, dict) else None


def merge_place(base: PlaceRecord, detail: PlaceRecord) -> PlaceRecord:
    """Overlay the fields the place lookup filled in, keeping the search result."""
    filled = {name: value for name, value in detail.model_dump().items() if value is not None}
    return base.model_copy(update=filled)
