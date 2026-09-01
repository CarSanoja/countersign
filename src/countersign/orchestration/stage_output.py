"""Risk, generation and delivery: the three stages that produce something.

The risk stage makes no tool call and therefore leaves no gate entry: the
synthesiser holds no capability by design, and reads only what the earlier
stages already collected.

The delivery stage asks for ``signature.execute`` on every run, whether or not
an envelope exists, and is refused. A power that is never requested leaves no
evidence that it is unavailable, so the refusal is produced deliberately and
kept in the trace.
"""

from typing import Any

from countersign.agents.risk_synthesizer import UngroundedVerdictError
from countersign.fleet.roster import DOCUMENT_DRAFTER_ID, ENVELOPE_PREPARER_ID
from countersign.orchestration.evidence import build_bundle
from countersign.orchestration.gate import guarded, refuse
from countersign.orchestration.stages import Stage, skipped
from countersign.orchestration.state import RunState
from countersign.schemas.verdict import RiskLevel, Verdict

GENERATE_TOOL = "doctavian_generate_document"
PREPARE_TOOL = "foxit_prepare_envelope"
SIGNATURE_TOOL = "foxit_execute_signature"


async def run_risk(state: RunState) -> None:
    """Fuse the collected evidence into a verdict, or refuse to produce one."""
    bundle = build_bundle(
        state.run_id,
        state.legal_name or state.document_ref,
        invoice=state.invoice,
        assessment=state.assessment,
        sweep=state.sweep,
    )
    if bundle is None:
        state.skip(
            skipped(
                Stage.RISK,
                "no earlier stage produced citable evidence, so no verdict is possible",
            )
        )
        return
    if state.blocked_by_credentials(Stage.RISK):
        return
    try:
        verdict = await state.ports.synthesize(bundle)
    except UngroundedVerdictError as error:
        state.failed(Stage.RISK, str(error))
        return
    except Exception as error:
        state.failed(Stage.RISK, f"{type(error).__name__}: {error}")
        return
    state.verdict = verdict
    state.completed(
        Stage.RISK,
        f"{verdict.level.value} at score {verdict.score:.2f} on {len(verdict.signals)} signal(s), "
        f"from {len(bundle.items)} evidence item(s)",
    )


async def run_generation(state: RunState) -> None:
    """Render the out-of-band confirmation document, when the verdict calls for one."""
    verdict = state.verdict
    if verdict is None:
        state.skip(skipped(Stage.GENERATION, "no verdict was reached, so nothing is drafted"))
        return
    if verdict.level is RiskLevel.CLEAR:
        state.skip(
            skipped(Stage.GENERATION, "the verdict is clear; no counter-document is called for")
        )
        return
    if not state.config.template_path.strip():
        state.skip(
            skipped(Stage.GENERATION, "no template is configured; set RunConfig.template_path")
        )
        return
    if state.blocked_by_credentials(Stage.GENERATION):
        return
    try:
        result = await guarded(
            state.trace,
            DOCUMENT_DRAFTER_ID,
            GENERATE_TOOL,
            lambda: state.ports.generate(
                state.config.template_path,
                document_payload(state, verdict),
                state.config.document_name,
            ),
        )
    except Exception as error:
        state.failed(Stage.GENERATION, f"{type(error).__name__}: {error}")
        return
    if not result.ok:
        state.failed(Stage.GENERATION, result.error or "the generator returned no document")
        return
    state.document = dict(result.payload)
    state.completed(Stage.GENERATION, f"{state.config.document_name} rendered")


async def run_delivery(state: RunState) -> None:
    """Prepare the envelope and stop. The signature is asked for and denied."""
    refuse(state.trace, ENVELOPE_PREPARER_ID, SIGNATURE_TOOL)
    document_url = _document_url(state)
    if not document_url:
        state.skip(
            skipped(Stage.DELIVERY, "no document exists to sign, so no envelope is prepared")
        )
        return
    if not state.config.parties:
        state.skip(skipped(Stage.DELIVERY, "no signing party is configured; set RunConfig.parties"))
        return
    if state.blocked_by_credentials(Stage.DELIVERY):
        return
    try:
        result = await guarded(
            state.trace,
            ENVELOPE_PREPARER_ID,
            PREPARE_TOOL,
            lambda: state.ports.prepare_envelope(
                document_url,
                state.config.document_name,
                state.config.parties,
                state.config.fields,
            ),
        )
    except Exception as error:
        state.failed(Stage.DELIVERY, f"{type(error).__name__}: {error}")
        return
    if not result.ok:
        state.failed(Stage.DELIVERY, result.error or "the envelope was not prepared")
        return
    state.envelope = dict(result.payload)
    state.completed(
        Stage.DELIVERY,
        f"envelope {state.envelope.get('folder_id')} left in draft, awaiting a human signer",
    )


def document_payload(state: RunState, verdict: Verdict) -> dict[str, Any]:
    """The fields the confirmation template merges. Data, never prose."""
    return {
        "run_id": state.run_id,
        "document_ref": state.document_ref,
        "legal_name": state.legal_name,
        "address": state.address,
        "official_domain": state.official_domain,
        "sender_domain": state.sender_domain,
        "risk_level": verdict.level.value,
        "risk_score": round(verdict.score, 2),
        "headline": verdict.headline,
        "recommended_action": verdict.recommended_action,
        "signals": [
            {
                "kind": signal.kind.value,
                "weight": signal.weight,
                "statement": signal.claim.statement,
                "sources": [source.locator for source in signal.claim.sources],
            }
            for signal in verdict.signals
        ],
        "decided_at": verdict.decided_at,
    }


def _document_url(state: RunState) -> str:
    """The URL Foxit will fetch the document from.

    Doctavian hands back a storage urn and, at most, a local path; neither is a
    URL another service can retrieve. So a configured url wins, and the payload
    is only consulted in case a hosting step upstream added one.
    """
    configured = state.config.document_url.strip()
    if configured:
        return configured
    for key in ("download_url", "url"):
        value = state.document.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


__all__ = [
    "GENERATE_TOOL",
    "PREPARE_TOOL",
    "SIGNATURE_TOOL",
    "document_payload",
    "run_delivery",
    "run_generation",
    "run_risk",
]
