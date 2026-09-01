"""The stage that makes the trace outlive the process.

The harness principal writes it, not one of the seven: no agent in the roster
holds backend.persist, which is correct, because the writer of an audit trail
should not be one of the parties it is auditing. Its two backend capabilities
are declared in `gate`, and both writes still go through the same gate, so the
decision to persist appears in the very trace being persisted.

Order is deliberate. Both gate decisions are recorded before the rows are read,
so the last row of every run is the run's own decision to write itself down.
"""

from typing import Any

from autocurricula.schemas.common import utc_now
from autocurricula.tools.base import ToolResult

from countersign.orchestration.baseline import baseline_columns, baseline_configured
from countersign.orchestration.gate import HARNESS_ID, authorize, guarded
from countersign.orchestration.sink import TraceSink
from countersign.orchestration.stages import Stage, skipped
from countersign.orchestration.state import RunState
from countersign.tools.xano import xano_persist_vendor

AUDIT_TOOL = "xano_append_audit"
VENDOR_TOOL = "xano_persist_vendor"


async def run_persistence(state: RunState, sink: TraceSink) -> None:
    """Write the vendor row and then the whole trace, and record both decisions."""
    if state.blocked_by_credentials(Stage.PERSISTENCE):
        return
    errors: list[str] = []
    vendor = await _persist_vendor(state)
    if not vendor.ok:
        errors.append(vendor.error or "the vendor row was not persisted")
    refusal = authorize(state.trace, HARNESS_ID, AUDIT_TOOL)
    if refusal is not None:
        state.skip(skipped(Stage.PERSISTENCE, refusal.reason))
        return
    try:
        written = await sink.write(state.trace.rows())
    except Exception as error:
        state.failed(Stage.PERSISTENCE, f"{type(error).__name__}: {error}")
        return
    if not written.ok:
        state.failed(Stage.PERSISTENCE, written.error or "the trace was not persisted")
        return
    state.trace_persisted = True
    state.completed(
        Stage.PERSISTENCE,
        f"{written.payload.get('written', len(state.trace))} audit row(s) written",
        errors,
    )


async def _persist_vendor(state: RunState) -> ToolResult:
    try:
        return await guarded(
            state.trace,
            HARNESS_ID,
            VENDOR_TOOL,
            lambda: xano_persist_vendor(vendor_row(state)),
        )
    except Exception as error:
        return ToolResult.failure(f"{type(error).__name__}: {error}")


def vendor_row(state: RunState) -> dict[str, Any]:
    """The counterparty as the workflow knows it at the end of the run."""
    verdict = state.verdict
    return {
        "run_id": state.run_id,
        "document_ref": state.document_ref,
        "legal_name": state.legal_name,
        "address": state.address,
        "official_domain": state.official_domain,
        "sender_domain": state.sender_domain,
        "risk_level": verdict.level.value if verdict is not None else "unassessed",
        "risk_score": round(verdict.score, 2) if verdict is not None else 0.0,
        "headline": verdict.headline if verdict is not None else "",
        "recommended_action": verdict.recommended_action if verdict is not None else "",
        "decided_at": verdict.decided_at if verdict is not None else "",
        "skipped_stages": [entry.stage.value for entry in state.skipped],
        **_bank_file(state),
    }


def _bank_file(state: RunState) -> dict[str, str]:
    """The account this run saw, so the next run has something to compare against.

    Only the fingerprint is stored, never the account. A vendor acquires a file
    the first time an invoice from them is assessed, which is what turns the
    bank-change signal from a phrase match into a comparison.
    """
    invoice = state.invoice
    if invoice is None or invoice.iban is None or not baseline_configured():
        return {}
    verdict = state.verdict
    at = verdict.decided_at if verdict is not None else utc_now().isoformat()
    try:
        return baseline_columns(invoice.iban.value, at)
    except Exception:
        return {}


__all__ = ["AUDIT_TOOL", "VENDOR_TOOL", "run_persistence", "vendor_row"]
