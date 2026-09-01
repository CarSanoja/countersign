"""What COUNTERSIGN keeps from a SerpApi response.

Every field is optional because every block of a SERP is optional: Google
decides on the day whether a knowledge graph, a local pack or a phone number
comes back, and a counterparty check cannot assume any of them exist.
"""

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field


class OrganicResult(StrictBaseModel):
    position: int | None = None
    title: str | None = None
    link: str | None = None
    displayed_link: str | None = None
    snippet: str | None = None
    source: str | None = None


class KnowledgeGraphSummary(StrictBaseModel):
    title: str | None = None
    website: str | None = None
    entity_type: str | None = None
    description: str | None = None


class OfficialSiteEvidence(StrictBaseModel):
    query: str
    search_id: str | None = None
    organic_results: list[OrganicResult] = Field(default_factory=list)
    knowledge_graph: KnowledgeGraphSummary | None = None


class NewsItem(StrictBaseModel):
    position: int | None = None
    title: str | None = None
    link: str | None = None
    source_name: str | None = None
    authors: list[str] = Field(default_factory=list)
    iso_date: str | None = None


class AdverseMediaEvidence(StrictBaseModel):
    query: str
    when_window: str | None = None
    search_id: str | None = None
    items: list[NewsItem] = Field(default_factory=list)


class PlaceRecord(StrictBaseModel):
    """A Google Maps business listing.

    maps_place_id is the 'ChIJ...' identifier of the google_maps engine, which
    is a different thing from the numeric place_id that engine=google and
    engine=google_local return; that one is the CID and is kept as data_cid.
    """

    position: int | None = None
    title: str | None = None
    maps_place_id: str | None = None
    data_cid: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    rating: float | None = None
    reviews: int | None = None
    place_type: str | None = None
    open_state: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class AddressEvidence(StrictBaseModel):
    query: str
    search_id: str | None = None
    places: list[PlaceRecord] = Field(default_factory=list)
    details_fetched: bool = False
    details_error: str | None = None
