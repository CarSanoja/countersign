"""The rates a soak exists to produce, the false positive rate first.

Every rate here names its denominator, because the interesting ones disagree. A
legitimate invoice sent to review is a false positive to the finance team that
now has to phone somebody; a legitimate invoice sent to high is a stopped
payment. One number for both would hide the difference that decides whether the
control stays switched on. Runs that reached no verdict at all are counted
apart, and never quietly read as clearances.
"""

from corpus import CASES, SoakCase
from runner import Observation

FLAGGED = ("review", "high")
BLOCKING = "high"
BY_ID: dict[str, SoakCase] = {case.case_id: case for case in CASES}


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank, so the number reported is one that was actually observed."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), round(fraction * len(ordered) + 0.5)))
    return ordered[rank - 1]


def _split(observations: list[Observation]) -> tuple[list[Observation], list[Observation]]:
    legit = [o for o in observations if not BY_ID[o.case_id].fraudulent]
    fraud = [o for o in observations if BY_ID[o.case_id].fraudulent]
    return legit, fraud


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def false_positive_rows(observations: list[Observation]) -> dict[str, object]:
    """The rate that decides whether a control survives its second week."""
    legit, _ = _split(observations)
    decided = [o for o in legit if o.level is not None]
    flagged = [o for o in decided if o.level in FLAGGED]
    blocking = [o for o in decided if o.level == BLOCKING]
    return {
        "legitimate_runs": len(legit),
        "legitimate_runs_with_verdict": len(decided),
        "false_positive_rate": _rate(len(flagged), len(decided)),
        "false_positives": f"{len(flagged)}/{len(decided)}",
        "blocking_false_positive_rate": _rate(len(blocking), len(decided)),
        "blocking_false_positives": f"{len(blocking)}/{len(decided)}",
        "flagged_legitimate_cases": sorted({o.case_id for o in flagged}),
        "blocked_legitimate_cases": sorted({o.case_id for o in blocking}),
    }


def detection_rows(observations: list[Observation]) -> dict[str, object]:
    """What the same runs caught, so the false positive rate is not read alone."""
    _, fraud = _split(observations)
    decided = [o for o in fraud if o.level is not None]
    caught = [o for o in decided if o.level == BLOCKING]
    flagged = [o for o in decided if o.level in FLAGGED]
    missed = [o for o in decided if o.level not in FLAGGED]
    return {
        "fraudulent_runs": len(fraud),
        "detection_rate": _rate(len(caught), len(decided)),
        "detected_high": f"{len(caught)}/{len(decided)}",
        "flagged_at_all": f"{len(flagged)}/{len(decided)}",
        "missed_cases": sorted({o.case_id for o in missed}),
    }


def stability_rows(observations: list[Observation]) -> dict[str, object]:
    """Whether the verdict reached in one pass is the verdict reached in the next."""
    levels: dict[str, set[str | None]] = {}
    signals: dict[str, set[tuple[str, ...]]] = {}
    for observation in observations:
        levels.setdefault(observation.case_id, set()).add(observation.level)
        signals.setdefault(observation.case_id, set()).add(observation.signals)
    stable_level = [case for case, seen in levels.items() if len(seen) == 1]
    stable_signals = [case for case, seen in signals.items() if len(seen) == 1]
    return {
        "level_stable": f"{len(stable_level)}/{len(levels)}",
        "signal_set_stable": f"{len(stable_signals)}/{len(signals)}",
        "cases_that_moved": sorted(set(levels) - set(stable_level)),
        "cases_whose_signals_moved": sorted(set(signals) - set(stable_signals)),
    }


def _accumulated(runs: list[Observation]) -> dict[str, float]:
    """What one expediente cost across every pass it went through."""
    totals: dict[str, float] = {}
    for run in runs:
        for unit, amount in run.cost.items():
            totals[unit] = round(totals.get(unit, 0.0) + amount, 2)
    return totals


def case_table(observations: list[Observation]) -> list[dict[str, object]]:
    """One row per case: its ground truth, every verdict it got, and what it cost."""
    rows: list[dict[str, object]] = []
    for case in CASES:
        runs = sorted(
            [o for o in observations if o.case_id == case.case_id],
            key=lambda observation: observation.pass_index,
        )
        if not runs:
            continue
        decided = [run for run in runs if run.level is not None]
        witness = decided[0] if decided else runs[0]
        rows.append(
            {
                "case_id": case.case_id,
                "truth": "fraud" if case.fraudulent else "legitimate",
                "sender_domain": case.sender_domain,
                "official_domain": case.counterparty.official_domain,
                "bank_change_announced": case.bank_changed,
                "levels": [run.level for run in runs],
                "stable": len({run.level for run in runs}) == 1,
                "scores": [run.score for run in runs],
                "signals": list(witness.signals),
                "seconds": [run.seconds for run in runs],
                "cost_accumulated": _accumulated(runs),
                "stages": runs[-1].stages,
                "errors": sorted({error for run in runs for error in run.errors}),
                "why": case.why,
            }
        )
    return rows


__all__ = [
    "BLOCKING",
    "BY_ID",
    "FLAGGED",
    "case_table",
    "detection_rows",
    "false_positive_rows",
    "percentile",
    "stability_rows",
]
