"""Turning three stages of output into the one index a verdict may cite.

The synthesiser never receives prose. It receives items addressable by id whose
text is the material that was actually retrieved, so a citation the model
invents cannot resolve and the grounding check can say no. This module is where
each stage's output is reduced to that, and anything without retrieved text is
left out rather than padded with a restatement of the claim it supports.
"""

from autocurricula.schemas.common import utc_now

from countersign.agents.counterparty_verifier import CounterpartyAssessment
from countersign.agents.document_extractor import ExtractedInvoice
from countersign.agents.document_extractor_fields import InvoiceField
from countersign.agents.risk_evidence import EvidenceBundle, EvidenceChannel, EvidenceItem
from countersign.agents.risk_weights import SIGNAL_WEIGHTS
from countersign.orchestration.baseline import (
    VendorBaseline,
    bank_signal,
    baseline_configured,
)
from countersign.orchestration.domain_sweep import DomainSweep
from countersign.schemas.evidence import Claim, Provider, SourceRef
from countersign.schemas.verdict import RiskSignal, SignalKind

OCCUPIED = (
    "{name} is a {kind} variant of {official} and is already registered; the "
    "registry reports it is not available, so that surface is occupied. Who holds "
    "it is not answered by an availability check."
)
SENDER_FREE = (
    "{sender} is the domain the invoice was sent from and it is not registered "
    "in the {environment} registry."
)
ANNOUNCED = (
    "The document announces new bank details ({phrase!r}). No vendor file is "
    "configured on this instance, so this rests on what the document says about "
    "itself and not on a comparison against the account on record."
)


def extraction_items(invoice: ExtractedInvoice) -> list[EvidenceItem]:
    """One item per anchored field, quoting the page span it was read from."""
    items: list[EvidenceItem] = []
    for name in InvoiceField:
        field = invoice.field(name)
        if field is None or not field.source.snippet.strip():
            continue
        items.append(
            EvidenceItem(
                evidence_id=f"D{len(items) + 1}",
                channel=EvidenceChannel.EXTRACTION,
                text=field.source.snippet,
                source=field.source,
            )
        )
    return items


def verification_items(assessment: CounterpartyAssessment) -> list[EvidenceItem]:
    """One item per distinct retrieved snippet the verifier relied on."""
    claims = [*assessment.claims, *[signal.claim for signal in assessment.signals]]
    seen: set[tuple[str, str, str]] = set()
    items: list[EvidenceItem] = []
    for claim in claims:
        for source in claim.sources:
            key = (source.provider.value, source.locator, source.snippet.strip())
            if not source.snippet.strip() or key in seen:
                continue
            seen.add(key)
            items.append(
                EvidenceItem(
                    evidence_id=f"V{len(items) + 1}",
                    channel=EvidenceChannel.VERIFICATION,
                    text=source.snippet,
                    source=source,
                )
            )
    return items


def sweep_items(sweep: DomainSweep) -> list[EvidenceItem]:
    """The registry's answers, written out as the sentences a claim may quote."""
    items: list[EvidenceItem] = []
    for finding in sweep.occupied_high_risk:
        items.append(
            EvidenceItem(
                evidence_id=f"S{len(items) + 1}",
                channel=EvidenceChannel.DOMAIN_SWEEP,
                text=OCCUPIED.format(
                    name=finding.domain_name, kind=finding.kind, official=sweep.official_domain
                ),
                source=_namecom_source(finding.domain_name, sweep.swept_at),
            )
        )
    if sweep.sender_registered is False and sweep.sender_domain:
        items.append(
            EvidenceItem(
                evidence_id=f"S{len(items) + 1}",
                channel=EvidenceChannel.DOMAIN_SWEEP,
                text=SENDER_FREE.format(
                    sender=sweep.sender_domain, environment=sweep.environment
                ),
                source=_namecom_source(sweep.sender_domain, sweep.swept_at),
            )
        )
    return items


def _official_source(assessment: CounterpartyAssessment | None) -> SourceRef | None:
    """Which search result established the vendor's real domain.

    The comparison that drives the whole verdict is sender against official, and
    the official half is discovered, not given. Citing only the registry would
    credit name.com for an answer SerpApi supplied.
    """
    if assessment is None or not assessment.official_domain:
        return None
    for claim in assessment.claims:
        for source in claim.sources:
            names_it = assessment.official_domain in claim.statement
            if source.provider is Provider.SERPAPI and names_it:
                return source
    return None


def _established_signals(
    sweep: DomainSweep, at: str, official_source: SourceRef | None = None
) -> list[RiskSignal]:
    """Turn the registry's settled facts into signals the model cannot drop."""
    statements = sweep.established_claims()
    sender_is_official = bool(sweep.sender_domain) and (
        sweep.sender_domain == sweep.official_domain
    )
    signals: list[RiskSignal] = []
    for kind in sweep.established_signals():
        if kind is SignalKind.CONFUSABLE_ALREADY_REGISTERED and sender_is_official:
            continue
        statement = statements.get(kind)
        if statement is None:
            continue
        sources = [
            SourceRef(
                provider=Provider.NAMECOM,
                locator=sweep.sender_domain or sweep.official_domain,
                snippet=f"checkAvailability against {sweep.environment}",
                retrieved_at=sweep.swept_at or at,
            )
        ]
        if kind is SignalKind.SENDER_DOMAIN_NOT_OFFICIAL and official_source is not None:
            sources.append(official_source)
        signals.append(
            RiskSignal(
                kind=kind,
                weight=SIGNAL_WEIGHTS[kind],
                claim=Claim(statement=statement, sources=sources, confidence=1.0),
            )
        )
    return signals


def build_bundle(
    run_id: str,
    subject: str,
    *,
    invoice: ExtractedInvoice | None = None,
    assessment: CounterpartyAssessment | None = None,
    sweep: DomainSweep | None = None,
    baseline: VendorBaseline | None = None,
) -> EvidenceBundle | None:
    """Assemble the index, or None when no stage produced anything citable.

    `baseline` is the vendor's file as `baseline.known_bank` read it, and is
    passed in rather than fetched here so this stays a pure function of what the
    stages collected: the one network read the bank comparison needs belongs to
    the caller that already owns the run's credentials and its trace.
    """
    at = utc_now().isoformat()
    items: list[EvidenceItem] = []
    required: list[SignalKind] = []
    established: list[RiskSignal] = []
    suppressed: list[SignalKind] = []
    if invoice is not None:
        items.extend(extraction_items(invoice))
        bank = _bank_signal(invoice, baseline, at)
        if bank is not None:
            established.append(bank)
    if assessment is not None and assessment.usable_for_verdict:
        items.extend(verification_items(assessment))
        established.extend(assessment.signals)
    if sweep is not None:
        items.extend(sweep_items(sweep))
        required = sweep.established_signals()
        established.extend(_established_signals(sweep, at, _official_source(assessment)))
        if sweep.sender_domain and sweep.sender_domain == sweep.official_domain:
            suppressed.append(SignalKind.CONFUSABLE_ALREADY_REGISTERED)
    if not items:
        return None
    return EvidenceBundle(
        run_id=run_id,
        subject=subject,
        items=items,
        required_signals=[kind for kind in required if _backed(kind, items)],
        established_signals=established,
        suppressed_signals=suppressed,
    )


def _bank_signal(
    invoice: ExtractedInvoice, baseline: VendorBaseline | None, at: str
) -> RiskSignal | None:
    """The comparison where a vendor file exists, the phrase where none can.

    The fallback is kept because an instance with no Xano credentials still has
    to say something about a document announcing new bank details, and the phrase
    match is all there is. It is the degraded answer and never the preferred one:
    it reports what the sender chose to write, which is exactly the thing an
    attacker controls.
    """
    if baseline_configured():
        return bank_signal(invoice, baseline, at)
    if invoice.bank_change is None:
        return None
    return RiskSignal(
        kind=SignalKind.BANK_DETAILS_CHANGED,
        weight=SIGNAL_WEIGHTS[SignalKind.BANK_DETAILS_CHANGED],
        claim=Claim(
            statement=ANNOUNCED.format(phrase=invoice.bank_change.value),
            sources=[invoice.bank_change.source],
            confidence=1.0,
        ),
    )


def _backed(kind: SignalKind, items: list[EvidenceItem]) -> bool:
    """Never demand a signal the index cannot support; that is unfalsifiable."""
    sweep_texts = [item for item in items if item.channel == EvidenceChannel.DOMAIN_SWEEP]
    if kind is SignalKind.CONFUSABLE_ALREADY_REGISTERED:
        return any("already registered" in item.text for item in sweep_texts)
    if kind is SignalKind.SENDER_DOMAIN_UNREGISTERED:
        return any("is not registered" in item.text for item in sweep_texts)
    return False


def _namecom_source(domain_name: str, at: str) -> SourceRef:
    return SourceRef(
        provider=Provider.NAMECOM, locator=domain_name, snippet="", retrieved_at=at
    )


__all__ = [
    "build_bundle",
    "extraction_items",
    "sweep_items",
    "verification_items",
]
