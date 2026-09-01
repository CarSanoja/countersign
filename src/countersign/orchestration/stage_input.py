"""Ingest, identity and domain: the three stages that gather what a verdict needs.

None of them raises. A provider that is unconfigured, a gate that refuses, a
model that will not answer: each ends as a recorded skip or a recorded failure,
and the run walks on with one less input rather than stopping.
"""

from autocurricula.tools.base import ToolResult

from countersign.agents.counterparty_verifier import AssessmentStatus
from countersign.agents.document_extractor import ExtractedInvoice
from countersign.fleet.roster import (
    COUNTERPARTY_VERIFIER_ID,
    DOCUMENT_EXTRACTOR_ID,
    DOMAIN_SENTINEL_ID,
)
from countersign.orchestration.domain_sweep import sweep_lookalikes
from countersign.orchestration.gate import authorize, guarded
from countersign.orchestration.stages import Stage, skipped
from countersign.orchestration.state import RunState

EXTRACT_TOOL = "nutrient_extract_fields"
DOMAIN_TOOL = "namecom_check_availability"
SEARCH_TOOLS = (
    "serpapi_find_official_site",
    "serpapi_adverse_media",
    "serpapi_verify_address",
)


async def run_ingest(state: RunState) -> None:
    """Parse the document into fields that each cite the span they came from."""
    if state.blocked_by_credentials(Stage.INGEST):
        return
    try:
        result = await guarded(
            state.trace,
            DOCUMENT_EXTRACTOR_ID,
            EXTRACT_TOOL,
            lambda: state.ports.extract(state.document_ref),
        )
    except Exception as error:
        state.failed(Stage.INGEST, f"{type(error).__name__}: {error}")
        return
    if not result.ok:
        state.failed(Stage.INGEST, result.error or "the extractor returned no invoice")
        return
    invoice = _invoice_from(result)
    if invoice is None:
        state.failed(Stage.INGEST, "the extractor returned a payload with no invoice in it")
        return
    state.invoice = invoice
    state.completed(
        Stage.INGEST,
        f"{len(invoice.present_fields)} fields anchored, {len(invoice.missing_fields)} absent",
        [f"{item.field} dropped: {item.reason}" for item in invoice.dropped],
    )


async def run_identity(state: RunState) -> None:
    """Decide whether the counterparty is the entity named, and whether it is in trouble."""
    name = state.legal_name
    if not name:
        state.skip(skipped(Stage.IDENTITY, "no legal name was extracted; nothing to verify"))
        return
    if state.blocked_by_credentials(Stage.IDENTITY):
        return
    refusals = [
        refusal
        for tool in SEARCH_TOOLS
        if (refusal := authorize(state.trace, COUNTERPARTY_VERIFIER_ID, tool)) is not None
    ]
    if refusals:
        state.skip(
            skipped(Stage.IDENTITY, "; ".join(refusal.reason for refusal in refusals))
        )
        return
    try:
        assessment = await state.ports.verify(name, state.address)
    except Exception as error:
        state.failed(Stage.IDENTITY, f"{type(error).__name__}: {error}")
        return
    state.assessment = assessment
    if assessment.status is AssessmentStatus.FAILED:
        state.failed(Stage.IDENTITY, "; ".join(assessment.errors) or "verification failed")
        return
    state.completed(
        Stage.IDENTITY,
        f"{len(assessment.signals)} signal(s), {assessment.searches_spent} search credit(s) spent",
        assessment.errors,
    )


async def run_domain(state: RunState) -> None:
    """Sweep the confusables of the official domain and report which are taken."""
    official = state.official_domain
    if not official:
        state.skip(
            skipped(
                Stage.DOMAIN,
                "no official domain was established, so there is nothing to sweep",
            )
        )
        return
    if state.blocked_by_credentials(Stage.DOMAIN):
        return
    refusal = authorize(state.trace, DOMAIN_SENTINEL_ID, DOMAIN_TOOL)
    if refusal is not None:
        state.skip(skipped(Stage.DOMAIN, refusal.reason))
        return
    try:
        sweep, error = await sweep_lookalikes(
            official,
            state.ports.check_domains,
            sender_domain=state.sender_domain,
            limit=state.config.sweep_limit,
        )
    except Exception as caught:
        state.failed(Stage.DOMAIN, f"{type(caught).__name__}: {caught}")
        return
    if sweep is None:
        state.failed(Stage.DOMAIN, error or "the registry returned nothing usable")
        return
    state.sweep = sweep
    state.completed(
        Stage.DOMAIN,
        f"{len(sweep.checked)} name(s) checked, {len(sweep.occupied_high_risk)} confusable(s) "
        "already registered",
        [f"{name} went unanswered" for name in sweep.unanswered],
    )


def _invoice_from(result: ToolResult) -> ExtractedInvoice | None:
    raw = result.payload.get("invoice")
    if not isinstance(raw, dict):
        return None
    try:
        return ExtractedInvoice.model_validate(raw)
    except ValueError:
        return None


__all__ = [
    "DOMAIN_TOOL",
    "EXTRACT_TOOL",
    "SEARCH_TOOLS",
    "run_domain",
    "run_identity",
    "run_ingest",
]
