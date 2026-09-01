"""The verdict, and the rule that makes it worth reading."""

from enum import StrEnum

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field, model_validator

from countersign.schemas.evidence import Claim


class RiskLevel(StrEnum):
    CLEAR = "clear"
    REVIEW = "review"
    HIGH = "high"


class SignalKind(StrEnum):
    """What the registry can and cannot tell us.

    Availability answers "is this registered", never "who owns it". A variant
    that is taken may well be the vendor's own defensive registration, so the
    signal is that the surface is occupied, not that someone is an attacker.
    """

    SENDER_DOMAIN_NOT_OFFICIAL = "sender_domain_not_official"
    SENDER_DOMAIN_UNREGISTERED = "sender_domain_unregistered"
    CONFUSABLE_ALREADY_REGISTERED = "confusable_already_registered"
    BANK_DETAILS_CHANGED = "bank_details_changed"
    ENTITY_NOT_FOUND = "entity_not_found"
    ADVERSE_MEDIA = "adverse_media"
    ADDRESS_NOT_A_BUSINESS = "address_not_a_business"


class RiskSignal(StrictBaseModel):
    kind: SignalKind
    weight: float = Field(ge=0.0, le=1.0)
    claim: Claim


class Verdict(StrictBaseModel):
    run_id: str = Field(min_length=1)
    level: RiskLevel
    headline: str = Field(min_length=1)
    signals: list[RiskSignal] = Field(default_factory=list)
    recommended_action: str = Field(min_length=1)
    decided_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def _high_risk_must_be_evidenced(self):
        """A HIGH verdict with no signals is an accusation with nothing behind it."""
        if self.level == RiskLevel.HIGH and not self.signals:
            raise ValueError("a high-risk verdict requires at least one evidenced signal")
        return self

    @property
    def score(self) -> float:
        return min(1.0, sum(signal.weight for signal in self.signals))
