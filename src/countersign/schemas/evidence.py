"""Provenance. A claim without a source is not a weak claim; it is an invalid one."""

from enum import StrEnum

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field, model_validator


class Provider(StrEnum):
    NUTRIENT = "nutrient"
    SERPAPI = "serpapi"
    NAMECOM = "namecom"
    DOCTAVIAN = "doctavian"
    FOXIT = "foxit"
    XANO = "xano"


class PageBox(StrictBaseModel):
    """Normalised to a fraction of the page, never raw pixels or points.

    The two Nutrient APIs disagree on units and the render DPI is undocumented,
    so a stored absolute box is a bug waiting for a different document size.
    """

    page: int = Field(ge=0)
    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class SourceRef(StrictBaseModel):
    provider: Provider
    locator: str = Field(min_length=1, description="URL, document id, or domain queried")
    box: PageBox | None = None
    snippet: str = ""
    retrieved_at: str = Field(min_length=1)


class Claim(StrictBaseModel):
    """One assertion the fleet is willing to put in front of a human."""

    statement: str = Field(min_length=1)
    sources: list[SourceRef] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sources_are_real(self):
        for source in self.sources:
            if not source.locator.strip():
                raise ValueError("a source with an empty locator does not support anything")
        return self
