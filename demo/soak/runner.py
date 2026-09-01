"""The corredor: the corpus, over and over, with the clock between passes.

A soak is not a benchmark run twice in a loop. Two things are deliberate here.
Reuse is turned off, because the pipeline can answer a document it has already
seen from the assessment on file, and a soak that measured that would be
measuring its own cache rather than the four providers. And the passes are
separated in time by a wait the caller sets, because a verdict that only holds
inside one minute has not been shown to hold at all.

The audit sink defaults to memory. Sixty runs write about eighteen hundred gate
decisions, and filling the demo workspace with them would be a side effect of
measuring, not a measurement.
"""

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from corpus import SoakCase
from documents import pdf_path
from meters import MeteredPorts, RunMeter

from countersign.orchestration import MemoryTraceSink, RunConfig, XanoTraceSink, run_assessment
from identity import IdentityBudget

SIGNATURE_TOOL = "foxit_execute_signature"
REUSE_MARKER = "byte-identical"


@dataclass(frozen=True)
class Observation:
    """One run of one invoice, as the report needs to read it."""

    case_id: str
    pass_index: int
    level: str | None
    score: float | None
    signals: tuple[str, ...]
    seconds: float
    stages: dict[str, str]
    errors: tuple[str, ...]
    provider_errors: tuple[str, ...]
    budget_violations: tuple[str, ...]
    identity_from_memo: bool
    signature_denied: bool
    reused_prior_assessment: bool
    cost: dict[str, float]


def _reuse_kwargs() -> dict[str, Any]:
    """Insist on re-running, without assuming the pipeline still offers the switch."""
    if "reuse" in inspect.signature(run_assessment).parameters:
        return {"reuse": False}
    return {}


def _stage_map(result: Any) -> dict[str, str]:
    return {outcome.stage.value: outcome.status.value for outcome in result.stages}


def _reused(result: Any) -> bool:
    return any(REUSE_MARKER in entry.reason for entry in result.skipped)


async def run_case(
    case: SoakCase, pass_index: int, budget: IdentityBudget, *, persist_audit: bool
) -> Observation:
    """One expediente end to end, timed and metered.

    Mutates external state: Nutrient processing credits, SerpApi credits when the
    budget allows a live verification, the name.com production registry as a read,
    Vertex, and the Xano row the pipeline writes for its own content key. No
    envelope is created and no document is rendered.
    """
    meter = RunMeter()
    ports = MeteredPorts(meter, budget)
    sink = XanoTraceSink() if persist_audit else MemoryTraceSink()
    started = time.monotonic()
    result = await run_assessment(
        pdf_path(case),
        run_id=f"soak-p{pass_index}-{case.case_id}",
        config=RunConfig(official_domain=case.counterparty.official_domain),
        ports=ports.ports(),
        sink=sink,
        **_reuse_kwargs(),
    )
    seconds = time.monotonic() - started
    verdict = result.verdict
    signals = tuple(sorted(signal.kind.value for signal in verdict.signals)) if verdict else ()
    return Observation(
        case_id=case.case_id,
        pass_index=pass_index,
        level=verdict.level.value if verdict else None,
        score=round(verdict.score, 2) if verdict else None,
        signals=signals,
        seconds=round(seconds, 2),
        stages=_stage_map(result),
        errors=tuple(result.errors),
        provider_errors=tuple(meter.provider_errors),
        budget_violations=tuple(meter.budget_violations),
        identity_from_memo=meter.identity_from_memo,
        signature_denied=any(
            entry.tool == SIGNATURE_TOOL and not entry.allowed for entry in result.trace
        ),
        reused_prior_assessment=_reused(result),
        cost=dict(meter.as_dict()),
    )


async def run_pass(
    cases: tuple[SoakCase, ...],
    pass_index: int,
    budget: IdentityBudget,
    *,
    persist_audit: bool,
    concurrency: int,
    on_run: Callable[[Observation], None] | None = None,
) -> list[Observation]:
    """One sweep of the whole corpus. Sequential by default, so latency is honest."""
    budget.start_pass()
    limit = asyncio.Semaphore(max(1, concurrency))
    observations: list[Observation] = []

    async def one(case: SoakCase) -> Observation:
        async with limit:
            observation = await run_case(case, pass_index, budget, persist_audit=persist_audit)
            if on_run is not None:
                on_run(observation)
            return observation

    if concurrency <= 1:
        for case in cases:
            observations.append(await one(case))
        return observations
    return list(await asyncio.gather(*(one(case) for case in cases)))


async def run_soak(
    cases: tuple[SoakCase, ...],
    *,
    passes: int,
    wait_seconds: float,
    budget: IdentityBudget,
    persist_audit: bool,
    concurrency: int,
    on_run: Callable[[Observation], None] | None = None,
    on_pass: Callable[[int, list[Observation]], None] | None = None,
) -> list[Observation]:
    """Every pass, with the configured wait between them and none after the last."""
    collected: list[Observation] = []
    for index in range(1, passes + 1):
        observations = await run_pass(
            cases,
            index,
            budget,
            persist_audit=persist_audit,
            concurrency=concurrency,
            on_run=on_run,
        )
        collected.extend(observations)
        if on_pass is not None:
            on_pass(index, observations)
        if index < passes and wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
    return collected


__all__ = ["REUSE_MARKER", "SIGNATURE_TOOL", "Observation", "run_case", "run_pass", "run_soak"]
