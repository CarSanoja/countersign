"""One document, six stages, one trace, and no stage allowed to stop the run.

What makes this an orchestration rather than a script is the two invariants it
holds across every stage. Every tool call is authorised against the capability
the roster granted its agent, and a tool that maps to no capability is denied,
so an unmapped name cannot be exercised by accident. And every decision the gate
takes, allowed or denied, is written to the ledger before the call happens, so
the trace is a record of what was attempted rather than of what succeeded.

Degradation is per provider. A missing key costs the stage that needs it and
nothing else: the stage is recorded as skipped, naming the variable, and the run
continues with one less input. The verdict a partial run reaches is still
grounded in what was actually collected, and the caller can see the gap.

The seventh thing a run does is decide whether to run at all. A document whose
bytes have already been assessed is answered from that assessment instead of
being pushed through the four providers and a second signature envelope, and
that decision is written down the same way a skipped stage is: six omissions,
each naming the run being quoted. Reuse is a choice this pipeline takes on the
record, never a duplicate silently avoided.
"""

from collections.abc import Callable

from autocurricula.schemas.common import utc_now

from countersign.fleet.roster import ENVELOPE_PREPARER_ID
from countersign.orchestration.gate import HARNESS_ID, guarded, refuse
from countersign.orchestration.idempotency import PriorRun, content_key, index_row, previous_run
from countersign.orchestration.ports import AssessmentPorts, RunConfig
from countersign.orchestration.result import AssessmentResult
from countersign.orchestration.sink import TraceSink, XanoTraceSink
from countersign.orchestration.stage_input import run_domain, run_identity, run_ingest
from countersign.orchestration.stage_output import (
    SIGNATURE_TOOL,
    run_delivery,
    run_generation,
    run_risk,
)
from countersign.orchestration.stage_persist import VENDOR_TOOL, run_persistence
from countersign.orchestration.stages import Stage, StageOutcome, skipped
from countersign.orchestration.state import RunState
from countersign.orchestration.trace import RunTrace
from countersign.schemas.verdict import Verdict
from countersign.tools.xano import xano_persist_vendor

StageObserver = Callable[[StageOutcome], None]
"""Called as each stage lands, so a caller can show progress while the run is
still going. Observation only: it cannot alter the run, and a run without one
behaves identically."""

RUN_ID_PREFIX = "countersign"

REUSED_STAGES: tuple[Stage, ...] = (
    Stage.INGEST,
    Stage.IDENTITY,
    Stage.DOMAIN,
    Stage.RISK,
    Stage.GENERATION,
    Stage.DELIVERY,
)
"""The six that cost something. Persistence is not among them: a reused run
still writes its own row and its own trace, or the reuse would leave no record."""


async def run_assessment(
    document_ref: str,
    *,
    run_id: str = "",
    config: RunConfig | None = None,
    ports: AssessmentPorts | None = None,
    sink: TraceSink | None = None,
    reuse: bool = True,
    on_stage: StageObserver | None = None,
) -> AssessmentResult:
    """Assess one document end to end and return the verdict, the trace and the gaps.

    Mutates external state through the stages that are configured: Nutrient
    credits, SerpApi credits, a Doctavian generation, a draft Foxit envelope and
    the Xano audit rows. It never executes a signature and never releases a
    payment; both capabilities are refused at the gate, on the record.

    Args:
        document_ref: the invoice to assess, as the extractor addresses it.
        run_id: the id every audit row carries; generated from the clock if empty.
        config: what the document cannot say, such as the template and the signer.
        ports: the six seams, live where not overridden.
        sink: where the trace is persisted; Xano when not overridden.
        on_stage: called with each stage outcome as it lands, for callers that
            need to show progress rather than wait for the whole run.
        reuse: answer from an assessment already on file for these exact bytes
            rather than assessing them again. Off means the world is re-checked
            on the same content, which is a caller's decision and not a default,
            because the accidental case — a retry, a resend, a double click —
            wants one envelope in front of the signer, not two.

    Returns:
        AssessmentResult carrying the Verdict when one was reached, the full
        trace of gate decisions, the stages that were omitted with the reason,
        and, when nothing was re-run, the earlier run it was quoted from.
    """
    if not document_ref.strip():
        raise ValueError("a run needs a document reference to assess")
    started_at = utc_now().isoformat()
    identifier = run_id.strip() or _generated_run_id(started_at)
    state = RunState(
        run_id=identifier,
        document_ref=document_ref.strip(),
        config=config or RunConfig(),
        ports=(ports or AssessmentPorts()).resolved(),
        trace=RunTrace(identifier),
        started_at=started_at,
    )
    key = content_key(state.document_ref)
    prior = await previous_run(key) if reuse and key else None
    if prior is None:
        seen = await _assess(state, key, on_stage)
    else:
        _quote(state, prior)
        seen = _emit(state, 0, on_stage)
    await run_persistence(state, sink if sink is not None else XanoTraceSink())
    _emit(state, seen, on_stage)
    return _result(state, key, prior)


def _emit(state: RunState, seen: int, on_stage: StageObserver | None) -> int:
    """Hand the observer every outcome recorded since it last looked."""
    if on_stage is not None:
        for outcome in state.outcomes[seen:]:
            on_stage(outcome)
    return len(state.outcomes)


async def _assess(state: RunState, key: str, on_stage: StageObserver | None = None) -> int:
    """Spend the providers, then leave the content key behind for the next run.

    Returns how many outcomes the observer has already been shown.
    """
    seen = 0
    for stage in (run_ingest, run_identity, run_domain, run_risk, run_generation, run_delivery):
        await stage(state)
        seen = _emit(state, seen, on_stage)
    verdict = state.verdict
    if key and verdict is not None:
        await _record_key(state, key, verdict)
    return seen


async def _record_key(state: RunState, key: str, verdict: Verdict) -> None:
    """Index this assessment by the bytes it assessed. Written before the trace is.

    The row goes out through the same gate as any other vendor write, and it goes
    out before persistence rather than after, so its decision is inside the trace
    persistence then writes rather than appended to a ledger already closed.
    """
    row = index_row(
        key,
        state.run_id,
        state.document_ref,
        verdict,
        legal_name=state.legal_name,
        official_domain=state.official_domain,
    )
    try:
        written = await guarded(
            state.trace, HARNESS_ID, VENDOR_TOOL, lambda: xano_persist_vendor(row)
        )
    except Exception as error:
        state.errors.append(f"idempotency: {type(error).__name__}: {error}")
        return
    if not written.ok:
        state.errors.append(
            f"idempotency: the content key was not recorded, so a rerun of this document "
            f"will be assessed again: {written.error}"
        )


def _quote(state: RunState, prior: PriorRun) -> None:
    """Adopt an earlier verdict and record, six times, that nothing was re-run.

    The signature is still asked for and still refused. A run that skipped every
    stage would otherwise be the one run in which the boundary this product is
    built on leaves no evidence of holding.
    """
    state.verdict = prior.verdict
    reason = (
        f"reused the assessment of {prior.summary} under content key "
        f"{prior.document_key}: the bytes are identical, so the six stages that spend "
        "something were not run and this retry raised no second signature envelope"
    )
    for stage in REUSED_STAGES:
        state.skip(skipped(stage, reason))
    refuse(state.trace, ENVELOPE_PREPARER_ID, SIGNATURE_TOOL)


def _generated_run_id(started_at: str) -> str:
    stamp = started_at.replace(":", "").replace("-", "").replace(".", "")
    return f"{RUN_ID_PREFIX}-{stamp}"


def _result(state: RunState, key: str, prior: PriorRun | None) -> AssessmentResult:
    return AssessmentResult(
        run_id=state.run_id,
        document_ref=state.document_ref,
        started_at=state.started_at,
        finished_at=utc_now().isoformat(),
        verdict=state.verdict,
        trace=list(state.trace.entries),
        skipped=list(state.skipped),
        stages=list(state.outcomes),
        document=state.document,
        envelope=state.envelope,
        trace_persisted=state.trace_persisted,
        errors=list(state.errors),
        document_key=key,
        reused_from=prior,
    )


__all__ = ["REUSED_STAGES", "RUN_ID_PREFIX", "run_assessment"]
