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
"""

from autocurricula.schemas.common import utc_now

from countersign.orchestration.ports import AssessmentPorts, RunConfig
from countersign.orchestration.result import AssessmentResult
from countersign.orchestration.sink import TraceSink, XanoTraceSink
from countersign.orchestration.stage_input import run_domain, run_identity, run_ingest
from countersign.orchestration.stage_output import run_delivery, run_generation, run_risk
from countersign.orchestration.stage_persist import run_persistence
from countersign.orchestration.state import RunState
from countersign.orchestration.trace import RunTrace

RUN_ID_PREFIX = "countersign"


async def run_assessment(
    document_ref: str,
    *,
    run_id: str = "",
    config: RunConfig | None = None,
    ports: AssessmentPorts | None = None,
    sink: TraceSink | None = None,
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

    Returns:
        AssessmentResult carrying the Verdict when one was reached, the full
        trace of gate decisions, and the stages that were omitted with the reason.
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
    await run_ingest(state)
    await run_identity(state)
    await run_domain(state)
    await run_risk(state)
    await run_generation(state)
    await run_delivery(state)
    await run_persistence(state, sink if sink is not None else XanoTraceSink())
    return _result(state)


def _generated_run_id(started_at: str) -> str:
    stamp = started_at.replace(":", "").replace("-", "").replace(".", "")
    return f"{RUN_ID_PREFIX}-{stamp}"


def _result(state: RunState) -> AssessmentResult:
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
    )


__all__ = ["RUN_ID_PREFIX", "run_assessment"]
