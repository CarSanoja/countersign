"""What the soak spent and how it behaved, as distinct from what it decided.

Latency, provider health and cost live apart from the rates because they answer
the other half of the same decision. The rates say whether the control is right;
these say whether anyone can afford to leave it running.
"""

from collections import Counter
from statistics import fmean

from metrics import percentile
from runner import Observation


def latency_rows(observations: list[Observation]) -> dict[str, object]:
    """p50 and p95, because the tail is what a payment queue actually feels."""
    seconds = [observation.seconds for observation in observations]
    by_pass = sorted({observation.pass_index for observation in observations})
    return {
        "runs": len(seconds),
        "p50_seconds": round(percentile(seconds, 0.50), 1),
        "p95_seconds": round(percentile(seconds, 0.95), 1),
        "max_seconds": round(max(seconds), 1) if seconds else 0.0,
        "mean_seconds": round(fmean(seconds), 1) if seconds else 0.0,
        "p50_by_pass": {
            str(index): round(
                percentile([o.seconds for o in observations if o.pass_index == index], 0.50), 1
            )
            for index in by_pass
        },
        "p95_by_pass": {
            str(index): round(
                percentile([o.seconds for o in observations if o.pass_index == index], 0.95), 1
            )
            for index in by_pass
        },
    }


def provider_rows(observations: list[Observation]) -> dict[str, object]:
    """Where the pipeline degraded, and which provider it degraded on."""
    statuses: dict[str, Counter[str]] = {}
    faults: Counter[str] = Counter()
    for observation in observations:
        for stage, status in observation.stages.items():
            statuses.setdefault(stage, Counter())[status] += 1
        for error in observation.provider_errors:
            faults[error.split(":", 1)[0]] += 1
    degraded = sum(
        count
        for counter in statuses.values()
        for status, count in counter.items()
        if status in ("degraded", "failed")
    )
    return {
        "stage_status": {stage: dict(counter) for stage, counter in sorted(statuses.items())},
        "provider_faults": dict(faults),
        "degraded_or_failed_stages": degraded,
        "runs_without_verdict": sum(1 for o in observations if o.level is None),
    }


def cost_rows(observations: list[Observation]) -> dict[str, object]:
    """What the whole soak spent, and what one expediente costs on average.

    The units are what the providers were actually asked for: the Nutrient figure
    is the cost the response header reported, not a price list quotation.
    """
    totals: Counter[str] = Counter()
    for observation in observations:
        for unit, amount in observation.cost.items():
            totals[unit] += amount
    runs = len(observations) or 1
    return {
        "total": {unit: round(amount, 2) for unit, amount in sorted(totals.items())},
        "per_expediente": {
            unit: round(amount / runs, 2) for unit, amount in sorted(totals.items())
        },
        "identity_served_from_memo": sum(1 for o in observations if o.identity_from_memo),
    }


def boundary_rows(observations: list[Observation]) -> dict[str, object]:
    """The invariants the soak must not have broken while measuring."""
    violations = sorted({v for o in observations for v in o.budget_violations})
    return {
        "signature_denied": f"{sum(1 for o in observations if o.signature_denied)}"
        f"/{len(observations)}",
        "generation_or_envelope_seams_reached": len(violations),
        "runs_answered_from_a_prior_assessment": sum(
            1 for o in observations if o.reused_prior_assessment
        ),
        "budget_violations": violations,
    }


__all__ = ["boundary_rows", "cost_rows", "latency_rows", "provider_rows"]
