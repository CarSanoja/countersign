"""The domain sentinel's stage: which confusables of the official domain are taken.

No model runs here, on purpose. Generating confusables and asking a registry who
already owns them is deterministic and reproducible, which is what makes it the
one signal that survives an audit unchanged.

Availability answers 'is this registered', never 'who owns it'. A taken variant
may be the vendor's own defensive registration, so the finding is that the
surface is occupied, and the wording of the evidence says exactly that.
"""

from collections.abc import Awaitable, Callable, Sequence

from autocurricula.schemas.common import StrictBaseModel, utc_now
from autocurricula.tools.base import ToolResult
from pydantic import Field

from countersign.domain.lookalike import (
    HIGH_RISK_KINDS,
    Variant,
    VariantKind,
    generate_variants,
)
from countersign.schemas.verdict import SignalKind

SWEEP_LIMIT = 24
DomainCheck = Callable[[list[str]], Awaitable[ToolResult]]


class DomainFinding(StrictBaseModel):
    """One confusable name and whether the registry says it is taken."""

    domain_name: str = Field(min_length=1)
    kind: str
    registered: bool
    high_risk: bool = False


class DomainSweep(StrictBaseModel):
    """What the registry answered about one official domain and its neighbours."""

    official_domain: str = Field(min_length=1)
    sender_domain: str = ""
    environment: str = "production"
    checked: list[str] = Field(default_factory=list)
    unanswered: list[str] = Field(default_factory=list)
    findings: list[DomainFinding] = Field(default_factory=list)
    sender_registered: bool | None = None
    swept_at: str = Field(min_length=1)

    @property
    def occupied(self) -> list[DomainFinding]:
        return [finding for finding in self.findings if finding.registered]

    @property
    def occupied_high_risk(self) -> list[DomainFinding]:
        return [finding for finding in self.occupied if finding.high_risk]

    def established_signals(self) -> list[SignalKind]:
        """The kinds the registry settled without anyone having to judge them."""
        signals: list[SignalKind] = []
        if self.sender_domain and self.sender_domain != self.official_domain:
            signals.append(SignalKind.SENDER_DOMAIN_NOT_OFFICIAL)
        if self.occupied_high_risk:
            signals.append(SignalKind.CONFUSABLE_ALREADY_REGISTERED)
        if self.sender_registered is False:
            signals.append(SignalKind.SENDER_DOMAIN_UNREGISTERED)
        return signals

    def established_claims(self) -> dict[SignalKind, str]:
        """What each settled kind actually asserts, in words a person can check."""
        held = len(self.occupied_high_risk)
        return {
            SignalKind.SENDER_DOMAIN_NOT_OFFICIAL: (
                f"The invoice was sent from {self.sender_domain}, which is not "
                f"{self.official_domain}, the vendor's official domain."
            ),
            SignalKind.CONFUSABLE_ALREADY_REGISTERED: (
                f"{held} confusable variant(s) of {self.official_domain} are already "
                f"registered, so the impersonation surface is occupied."
            ),
            SignalKind.SENDER_DOMAIN_UNREGISTERED: (
                f"{self.sender_domain} is not registered with any registrar, so the "
                f"invoice claims an address nobody owns."
            ),
        }


async def sweep_lookalikes(
    official_domain: str,
    check: DomainCheck,
    *,
    sender_domain: str = "",
    limit: int = SWEEP_LIMIT,
) -> tuple[DomainSweep | None, str | None]:
    """Ask the registry about the confusables, and about the sender if it differs."""
    official = official_domain.strip().lower().rstrip(".")
    if not official or "." not in official:
        return None, f"{official_domain!r} is not a domain the sweep can start from"
    sender = sender_domain.strip().lower().rstrip(".")
    variants = generate_variants(official, limit)
    names = [variant.domain_name for variant in variants]
    if sender and sender != official and sender not in names:
        names.append(sender)
    if not names:
        return None, f"no confusable variant could be generated for {official}"
    result = await check(names)
    if not result.ok:
        return None, result.error or "the registry returned no answer"
    return _assemble(official, sender, variants, result.payload), None


def _assemble(
    official: str,
    sender: str,
    variants: Sequence[Variant],
    payload: dict,
) -> DomainSweep:
    registered = {str(name) for name in payload.get("registered") or []}
    available = {str(name) for name in payload.get("available") or []}
    kinds: dict[str, VariantKind] = {v.domain_name: v.kind for v in variants}
    findings = [
        DomainFinding(
            domain_name=name,
            kind=kinds[name].value,
            registered=name in registered,
            high_risk=kinds[name] in HIGH_RISK_KINDS,
        )
        for name in kinds
        if name in registered or name in available
    ]
    sender_registered: bool | None = None
    if sender and sender != official:
        if sender in registered:
            sender_registered = True
        elif sender in available:
            sender_registered = False
    return DomainSweep(
        official_domain=official,
        sender_domain=sender,
        environment=str(payload.get("environment") or "production"),
        checked=[str(name) for name in payload.get("requested") or []],
        unanswered=[str(name) for name in payload.get("unanswered") or []],
        findings=findings,
        sender_registered=sender_registered,
        swept_at=utc_now().isoformat(),
    )


__all__ = [
    "SWEEP_LIMIT",
    "DomainCheck",
    "DomainFinding",
    "DomainSweep",
    "sweep_lookalikes",
]
