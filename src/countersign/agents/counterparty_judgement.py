"""What the model is allowed to say back.

Every judgement points at a retrieved result by index, never by URL. The
pipeline resolves the index into the link it actually fetched, so a citation
cannot be hallucinated: the worst a wrong index can do is name the wrong
retrieved result, which is a disagreement, not an invention.
"""

from enum import StrEnum

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field


class AdverseCategory(StrEnum):
    LITIGATION = "litigation"
    INSOLVENCY = "insolvency"
    FRAUD = "fraud"
    SANCTIONS = "sanctions"
    REGULATORY = "regulatory"
    OTHER = "other"


class OfficialSiteJudgement(StrictBaseModel):
    """Which retrieved result, if any, belongs to this legal entity."""

    result_index: int | None = None
    from_knowledge_graph: bool = False
    domain: str | None = None
    same_entity: bool
    reasoning: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class NewsJudgement(StrictBaseModel):
    """One news item, judged on identity first and adversity second.

    same_entity false ends the matter: a namesake's lawsuit says nothing about
    this counterparty, and adverse stays whatever the model wrote only so the
    dismissal can be read back in the audit trail.
    """

    item_index: int = Field(ge=0)
    same_entity: bool
    entity_reasoning: str = Field(min_length=1)
    adverse: bool
    category: AdverseCategory | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class AddressJudgement(StrictBaseModel):
    """Whether the invoiced address is this entity's real place of business."""

    place_index: int | None = None
    matches_entity: bool
    is_real_business: bool
    is_mail_drop: bool
    reasoning: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class CounterpartyJudgement(StrictBaseModel):
    """The whole answer, in one object, from one call."""

    official_site: OfficialSiteJudgement | None = None
    news: list[NewsJudgement] = Field(default_factory=list)
    address: AddressJudgement | None = None
    summary: str = Field(min_length=1)
