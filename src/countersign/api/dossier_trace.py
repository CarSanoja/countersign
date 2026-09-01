"""The trace, the stage strip, and everything that did not run.

The denied step is the product. It gets the seal colour, a heavier rule, its own
breathing room and the refusal spelled out in full, because a boundary nobody
can see on the screen is indistinguishable from a boundary nobody enforced.
"""

from collections.abc import Sequence

from countersign.api.dossier_view import StepView, step_views
from countersign.api.html import esc, join
from countersign.orchestration.stages import SkippedStage, StageOutcome
from countersign.orchestration.trace import TraceEntry

DENIED_LEAD = "Denied."
HUMAN_ONLY = "a capability reserved to a person"
NO_TRACE = "This run recorded no gate decision."
NO_SKIPS = "Every stage ran. Nothing was omitted for a missing credential."
NO_STAGES = ""


def step_notes(view: StepView) -> str:
    """One line for a call that went through, the full account for one refused."""
    if not view.allowed:
        reason = (
            f'<p class="reason"><b>{DENIED_LEAD}</b> {esc(view.reason)}</p>'
            if view.reason
            else ""
        )
        parts = [HUMAN_ONLY] if view.human_only else []
        parts.append(view.recorded_at)
        return join([reason, f'<p class="gate">{esc(" · ".join(parts))}</p>'])
    return ""


def render_step(view: StepView) -> str:
    """An allowed call is two quiet lines. A refused one takes the room it needs."""
    stamp = (
        f' <span class="box">{esc(view.recorded_at)}</span>'
        if view.allowed and view.recorded_at
        else ""
    )
    return join(
        [
            f'<li class="step step--{esc(view.status)}">',
            f'<span class="n">{view.ordinal}</span>',
            "<div>",
            f'<div class="who">{esc(view.display_name)} '
            f'<span class="stage">{esc(view.agent_id)}</span></div>',
            f'<div class="what">{esc(view.what)}{stamp}</div>',
            "</div>",
            f'<span class="pill">{esc(view.status)}</span>',
            step_notes(view),
            "</li>",
        ]
    )


def render_trace(trace: Sequence[TraceEntry]) -> str:
    if not trace:
        return f'<p class="empty">{esc(NO_TRACE)}</p>'
    rows = join(render_step(view) for view in step_views(trace))
    return f'<ol class="trace">{rows}</ol>'


def trace_tally(trace: Sequence[TraceEntry]) -> str:
    denied = sum(1 for entry in trace if not entry.allowed)
    steps = f"{len(trace)} decision{'' if len(trace) == 1 else 's'}"
    tallies = [f'<span class="tally">{esc(steps)}</span>']
    if denied:
        label = f"{denied} denied"
        tallies.append(f'<span class="tally tally--seal">{esc(label)}</span>')
    return join(tallies)


def render_stages(stages: Sequence[StageOutcome]) -> str:
    """The pipeline at a glance: one chip per stage, coloured by how it ended."""
    if not stages:
        return NO_STAGES
    chips = join(
        f'<li class="chip chip--{esc(outcome.status)}" title="{esc(outcome.detail)}">'
        f"{esc(outcome.stage)} · {esc(outcome.status)}</li>"
        for outcome in stages
    )
    return f'<ul class="strip">{chips}</ul>'


def render_skip(entry: SkippedStage) -> str:
    missing = (
        f'<div class="env">unset: {esc(", ".join(entry.missing_variables))}</div>'
        if entry.missing_variables
        else ""
    )
    return join(
        [
            '<li class="skip">',
            f'<div class="what">{esc(entry.stage)} · {esc(entry.provider)}</div>',
            f"<div>{esc(entry.reason)}</div>",
            missing,
            "</li>",
        ]
    )


def render_skipped(skipped: Sequence[SkippedStage]) -> str:
    if not skipped:
        return f'<p class="empty">{esc(NO_SKIPS)}</p>'
    return f'<ul class="skipped">{join(render_skip(entry) for entry in skipped)}</ul>'


def render_errors(errors: Sequence[str]) -> str:
    if not errors:
        return ""
    rows = join(f'<li class="error">{esc(error)}</li>' for error in errors)
    return f'<h2 class="sub">Stages that failed</h2><ul class="errors">{rows}</ul>'


__all__ = [
    "DENIED_LEAD",
    "HUMAN_ONLY",
    "NO_SKIPS",
    "NO_TRACE",
    "render_errors",
    "render_skip",
    "render_skipped",
    "render_stages",
    "render_step",
    "render_trace",
    "step_notes",
    "trace_tally",
]
