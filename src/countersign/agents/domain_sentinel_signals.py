"""Registry facts become claims, and only then signals.

Every locator here is a domain that was actually put in the request body, and
every snippet is the answer that came back for it, so a citation cannot point at
a name the sweep never asked about. Confidence is 1.0 and that is not bravado:
no judgement was made. The registry either answered that a name is taken or it
did not, and the claim says exactly that and nothing about who took it.

An unregistered sender raises two signals rather than one, because a sender that
nobody owns is also, necessarily, not the official domain. The weight table
scores that pair above the mismatch alone, which is how "worse" is expressed
here: by the arithmetic in `risk_weights`, never by a number chosen in this file.
"""

from countersign.agents.domain_sentinel_models import DomainSweep, VariantStatus, registry_line
from countersign.agents.risk_evidence import EvidenceChannel, EvidenceItem
from countersign.agents.risk_weights import weight_for
from countersign.schemas.evidence import Claim, Provider, SourceRef
from countersign.schemas.verdict import RiskSignal, SignalKind

REGISTRY_CONFIDENCE = 1.0
MAX_CITED_VARIANTS = 8

__all__ = ["MAX_CITED_VARIANTS", "sweep_evidence_items", "sweep_signals"]


def sweep_signals(
    *,
    sender_domain: str,
    official_domain: str,
    sender_is_official: bool,
    sender_registered: bool | None,
    variants: list[VariantStatus],
    environment: str,
    at: str,
) -> list[RiskSignal]:
    """Every signal the sweep is entitled to raise, and not one it cannot evidence."""
    signals = _sender_signals(
        sender_domain=sender_domain,
        official_domain=official_domain,
        sender_is_official=sender_is_official,
        sender_registered=sender_registered,
        environment=environment,
        at=at,
    )
    held = [variant for variant in variants if variant.registered]
    confusable = _confusable_signal(official_domain, held, environment, at)
    if confusable is not None:
        signals.append(confusable)
    return signals


def sweep_evidence_items(sweep: DomainSweep) -> list[EvidenceItem]:
    """The sweep as citable evidence, one item per name the registry answered.

    Ids are keyed on the domain so a sender that is itself one of the generated
    confusables produces one item, not two, which would fail the bundle's
    uniqueness check.
    """
    items: dict[str, EvidenceItem] = {}
    answered: list[tuple[str, bool]] = [
        (variant.domain_name, variant.registered) for variant in sweep.variants
    ]
    if sweep.sender_registered is not None:
        answered.append((sweep.sender_domain, sweep.sender_registered))
    if sweep.official_registered is not None:
        answered.append((sweep.official_domain, sweep.official_registered))
    for domain_name, registered in answered:
        line = registry_line(domain_name, registered, sweep.environment)
        items.setdefault(
            domain_name,
            EvidenceItem(
                evidence_id=f"namecom:{domain_name}",
                channel=EvidenceChannel.DOMAIN_SWEEP,
                text=line,
                source=_source(domain_name, registered, sweep.environment, sweep.checked_at),
            ),
        )
    return list(items.values())


def _sender_signals(
    *,
    sender_domain: str,
    official_domain: str,
    sender_is_official: bool,
    sender_registered: bool | None,
    environment: str,
    at: str,
) -> list[RiskSignal]:
    if not sender_domain:
        return []
    source = _source(sender_domain, bool(sender_registered), environment, at)
    signals: list[RiskSignal] = []
    if not sender_is_official:
        signals.append(
            _signal(
                SignalKind.SENDER_DOMAIN_NOT_OFFICIAL,
                f"This document was sent from {sender_domain}, which is not "
                f"{official_domain}, the domain of record for this counterparty.",
                [source],
            )
        )
    if sender_registered is False:
        signals.append(
            _signal(
                SignalKind.SENDER_DOMAIN_UNREGISTERED,
                f"{sender_domain} is not registered with any registrar, so no mailbox can "
                "exist at that domain and the sending address on this document cannot be "
                "the one it appears to be.",
                [source],
            )
        )
    return signals


def _confusable_signal(
    official_domain: str, held: list[VariantStatus], environment: str, at: str
) -> RiskSignal | None:
    if not held:
        return None
    cited = sorted(held, key=lambda variant: not variant.high_risk)[:MAX_CITED_VARIANTS]
    listed = ", ".join(f"{variant.domain_name} ({variant.kind.value})" for variant in cited)
    remainder = len(held) - len(cited)
    plural = "" if remainder == 1 else "s"
    more = f", and {remainder} further variant{plural}" if remainder > 0 else ""
    statement = (
        f"{len(held)} confusable variants of {official_domain} are already registered to "
        f"someone, including {listed}{more}. The registry answers whether a name is taken, "
        "never who holds it, so one of these may be a defensive registration by the "
        "counterparty itself."
    )
    sources = [
        _source(variant.domain_name, True, environment, at) for variant in cited
    ]
    return _signal(SignalKind.CONFUSABLE_ALREADY_REGISTERED, statement, sources)


def _signal(kind: SignalKind, statement: str, sources: list[SourceRef]) -> RiskSignal:
    """The weight comes from the fixed table, never from this agent."""
    return RiskSignal(
        kind=kind,
        weight=weight_for(kind),
        claim=Claim(statement=statement, sources=sources, confidence=REGISTRY_CONFIDENCE),
    )


def _source(domain_name: str, registered: bool, environment: str, at: str) -> SourceRef:
    return SourceRef(
        provider=Provider.NAMECOM,
        locator=domain_name,
        snippet=registry_line(domain_name, registered, environment),
        retrieved_at=at,
    )
