"""The verdict, and the honest block that stands in when there is not one.

`AssessmentResult.verdict` is optional because a run whose evidence never
arrived must still hand something back. A page that rendered that as a clear
result would be the worst failure this product could have, so the absence gets
its own block and names the stage that produced nothing.
"""

from countersign.agents.risk_weights import HIGH_THRESHOLD, REVIEW_THRESHOLD
from countersign.api.html import esc, join
from countersign.orchestration.result import AssessmentResult
from countersign.orchestration.stages import Stage
from countersign.schemas.verdict import RiskLevel, Verdict

LEVEL_LABEL: dict[RiskLevel, str] = {
    RiskLevel.CLEAR: "clear",
    RiskLevel.REVIEW: "review",
    RiskLevel.HIGH: "high risk",
}
NO_VERDICT = "This run reached no verdict, and nothing below should be read as one."
NO_REASON = "The risk stage produced nothing and recorded no reason."


def arithmetic(verdict: Verdict) -> str:
    """The score as a sum a person can redo with the weights printed above."""
    terms = " + ".join(f"{signal.weight:.2f}" for signal in verdict.signals) or "0.00"
    return (
        f"score {verdict.score:.2f} = {terms} · review at {REVIEW_THRESHOLD:.2f} · "
        f"high at {HIGH_THRESHOLD:.2f}"
    )


def verdict_block(verdict: Verdict) -> str:
    label = LEVEL_LABEL.get(verdict.level, str(verdict.level))
    return join(
        [
            f'<section class="verdict verdict--{esc(verdict.level)}">',
            f'<div class="level">{esc(label)}</div>',
            f'<p class="headline">{esc(verdict.headline)}</p>',
            '<p class="action"><b>Recommended action</b>'
            f"{esc(verdict.recommended_action)}</p>",
            f'<p class="arith">{esc(arithmetic(verdict))}</p>',
            "</section>",
        ]
    )


def no_verdict_reason(result: AssessmentResult) -> str:
    for entry in result.skipped:
        if entry.stage is Stage.RISK:
            return entry.reason
    return result.errors[0] if result.errors else NO_REASON


def no_verdict_block(result: AssessmentResult) -> str:
    return join(
        [
            '<section class="verdict verdict--none">',
            '<div class="level">no verdict</div>',
            f'<p class="headline">{esc(NO_VERDICT)}</p>',
            f'<p class="action"><b>Why</b>{esc(no_verdict_reason(result))}</p>',
            "</section>",
        ]
    )


def render_verdict(result: AssessmentResult) -> str:
    verdict = result.verdict
    return no_verdict_block(result) if verdict is None else verdict_block(verdict)


__all__ = [
    "LEVEL_LABEL",
    "NO_REASON",
    "NO_VERDICT",
    "arithmetic",
    "no_verdict_block",
    "no_verdict_reason",
    "render_verdict",
    "verdict_block",
]
