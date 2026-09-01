"""One full COUNTERSIGN run against live APIs and live models.

    set -a; . ./.env.local; set +a
    .venv/bin/python demo/run_demo.py
"""

import asyncio
import datetime
import uuid

from countersign.agents.document_extractor import ExtractedInvoice, extract_invoice
from countersign.agents.risk_evidence import EvidenceBundle, EvidenceChannel, EvidenceItem
from countersign.agents.risk_synthesizer import synthesize_verdict
from countersign.domain.lookalike import generate_variants
from countersign.fleet.capabilities import agent_holds, capability_for_tool
from countersign.models.vertex import flash, pro
from countersign.schemas.evidence import Provider, SourceRef
from countersign.schemas.verdict import SignalKind
from countersign.tools.namecom import namecom_check_availability

INVOICE = "demo/fixtures/invoice.pdf"
OFFICIAL_DOMAIN = "name.com"


async def run() -> None:
    now = datetime.datetime.now(datetime.UTC).isoformat()
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    print(f"=== {run_id} ===\n")

    result = await extract_invoice(INVOICE, flash(), ocr_language=None)
    if not result.ok:
        raise SystemExit(f"ingest failed: {result.error}")
    invoice = ExtractedInvoice.model_validate(result.payload[next(iter(result.payload))])
    sender = invoice.sender_domain.value
    print(f"1. INGESTA    {invoice.legal_name.value} · {sender} · {invoice.total_amount.value}")

    variants = generate_variants(OFFICIAL_DOMAIN, 40)
    sweep = await namecom_check_availability([sender] + [v.domain_name for v in variants])
    available = set(sweep.payload.get("available", []))
    taken = [v for v in variants if v.domain_name not in available]
    print(
        f"2. DOMINIO    oficial {OFFICIAL_DOMAIN} · "
        f"{len(taken)}/{len(variants)} confusables registradas"
    )

    bundle = EvidenceBundle(
        run_id=run_id,
        subject=invoice.legal_name.value,
        items=[
            EvidenceItem(
                evidence_id="e1",
                channel=EvidenceChannel.EXTRACTION,
                text=(
                    f"The invoice sender domain is {sender}. Total due "
                    f"{invoice.total_amount.value}. The document states the vendor "
                    "bank account has changed."
                ),
                source=invoice.sender_domain.source,
            ),
            EvidenceItem(
                evidence_id="e2",
                channel=EvidenceChannel.DOMAIN_SWEEP,
                text=(
                    f"{sender} is not {OFFICIAL_DOMAIN}, the vendor's official domain. "
                    f"{len(taken)} of {len(variants)} confusable variants of "
                    f"{OFFICIAL_DOMAIN} are already registered."
                ),
                source=SourceRef(
                    provider=Provider.NAMECOM, locator=sender,
                    snippet="checkAvailability", retrieved_at=now,
                ),
            ),
        ],
        required_signals=[
            SignalKind.SENDER_DOMAIN_NOT_OFFICIAL,
            SignalKind.CONFUSABLE_ALREADY_REGISTERED,
        ],
    )

    verdict = await synthesize_verdict(bundle, model=pro(), decided_at=now)
    print(f"\n3. VEREDICTO  {verdict.level.value.upper()}  score {verdict.score:.2f}")
    print(f"   {verdict.headline}")
    for signal in verdict.signals:
        sources = ", ".join(f"{s.provider.value}:{s.locator}" for s in signal.claim.sources)
        print(f"   · [{signal.kind.value}] {signal.claim.statement[:90]}  <- {sources}")

    print("\n4. ENTREGA    el agente intenta ejecutar la firma:")
    for tool in ("foxit_prepare_envelope", "foxit_execute_signature", "release_payment"):
        capability = capability_for_tool(tool)
        allowed = capability is not None and agent_holds(capability)
        print(f"   {tool:26} {str(capability):20} {'permitido' if allowed else 'DENEGADO'}")
    print(f"\n   {verdict.recommended_action}")


if __name__ == "__main__":
    asyncio.run(run())
