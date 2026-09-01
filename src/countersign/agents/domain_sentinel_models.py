"""What the lookalike sweep found, in the shape the rest of the fleet reads it.

Two classes come out of one registry answer, and they are not symmetric.
A confusable that is already owned is an impersonation surface that exists
today. A confusable that is still purchasable is only a surface someone could
take tomorrow, so it is worth taking first, and only when its attack class is
one a person actually falls for.

Availability answers whether a name is taken, never who holds it, so nothing
here is named after an attacker.
"""

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

from countersign.domain.lookalike import VariantKind
from countersign.schemas.verdict import RiskSignal, SignalKind


class VariantStatus(StrictBaseModel):
    """One confusable variant and what the registry said about it."""

    domain_name: str = Field(min_length=1)
    kind: VariantKind
    registered: bool
    high_risk: bool
    premium: bool = False
    purchase_price: float | None = None


class DomainSweep(StrictBaseModel):
    """One sweep: the official domain, its confusables, and the sender beside them.

    `sender_registered` and `official_registered` are tri-state on purpose. None
    means the registry never answered for that name, which is not the same as it
    being free, and reading the absence as free is the one mistake this sweep
    cannot make.
    """

    sender_domain: str
    official_domain: str
    environment: str
    checked_at: str = Field(min_length=1)
    sender_is_official: bool
    sender_registered: bool | None = None
    official_registered: bool | None = None
    variants: list[VariantStatus] = Field(default_factory=list)
    signals: list[RiskSignal] = Field(default_factory=list)
    unanswered: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def held_by_third_party(self) -> list[VariantStatus]:
        """Registered to someone: the impersonation surface that already exists."""
        return [variant for variant in self.variants if variant.registered]

    @property
    def defensive_targets(self) -> list[VariantStatus]:
        """Still purchasable and in a class that fools a reader: take these first."""
        return [
            variant
            for variant in self.variants
            if not variant.registered and variant.high_risk
        ]

    @property
    def signal_kinds(self) -> list[SignalKind]:
        """What the deterministic layer established, for the synthesiser to carry."""
        return [signal.kind for signal in self.signals]

    @property
    def answered(self) -> bool:
        return bool(self.variants) or self.sender_registered is not None


def registry_line(domain_name: str, registered: bool, environment: str) -> str:
    """The registry answer as one sentence, quoted verbatim by every citation.

    Claims and evidence items share this wording so that the span verifier is
    matching a quote against the exact text the sweep retrieved, rather than
    against a paraphrase of it.
    """
    state = "is already registered" if registered else "is unregistered and purchasable"
    return f"name.com {environment} availability check: {domain_name} {state}."
