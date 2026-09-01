"""The dossier page, assembled in the order a person needs to read it.

Verdict first, because that is the decision. Then every claim with the source it
rests on, because the decision is worth exactly as much as its provenance. Then
the trace, ending in the refusal. Then what never ran, and why.
"""

from typing import Any

from countersign.api.dossier_claims import render_signals
from countersign.api.dossier_style import DOSSIER_CSS
from countersign.api.dossier_trace import (
    render_errors,
    render_skipped,
    render_stages,
    render_trace,
    trace_tally,
)
from countersign.api.dossier_verdict import render_verdict
from countersign.api.html import esc, join, page
from countersign.orchestration.result import AssessmentResult

BRAND = "Countersign"
CLAIMS_LEDE = (
    "Every statement below cites the span or the result it came from. A statement "
    "that lost its source is printed as a defect, never as a finding."
)
TRACE_LEDE = (
    "Every decision the capability gate took, allowed or refused. The agent prepares "
    "the envelope; executing it is a capability no agent in the fleet holds."
)
SKIPPED_LEDE = "Stages omitted, and the variable each one was waiting for."
NO_CLAIMS = "No verdict was reached, so this run established no claim."
FOOTNOTE = (
    "Weights, score, level and recommended action come from a fixed table, not from a "
    "model. The model writes the prose and the citations only."
)
ENVELOPE_KEYS = ("folder_id", "folder_name", "folder_status", "dispatched")
AWAITING_KEY = "awaiting"


def fact(term: str, value: str) -> str:
    return f"<div><dt>{esc(term)}</dt><dd>{esc(value)}</dd></div>" if value else ""


def scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value) if isinstance(value, str | int | float) else ""


def masthead(result: AssessmentResult) -> str:
    facts = join(
        [
            fact("run", result.run_id),
            fact("started", result.started_at),
            fact("finished", result.finished_at),
            fact("trace persisted", "yes" if result.trace_persisted else "no"),
        ]
    )
    return join(
        [
            '<header class="masthead">',
            f'<div class="brand">{esc(BRAND)}</div>',
            f"<h1>{esc(result.document_ref)}</h1>",
            f'<dl class="facts">{facts}</dl>',
            "</header>",
        ]
    )


def envelope_facts(result: AssessmentResult) -> str:
    """What the handoff left behind, and what it is waiting for."""
    facts = join(fact(key, scalar(result.envelope.get(key))) for key in ENVELOPE_KEYS)
    awaiting = scalar(result.envelope.get(AWAITING_KEY))
    if not facts and not awaiting:
        return ""
    return join(
        [
            '<h2 class="sub">The envelope, left in draft</h2>',
            f'<dl class="facts">{facts}</dl>' if facts else "",
            f'<p class="action"><b>Awaiting</b>{esc(awaiting)}</p>' if awaiting else "",
        ]
    )


def claims_section(result: AssessmentResult) -> str:
    verdict = result.verdict
    signals = list(verdict.signals) if verdict is not None else []
    tally = f"{len(signals)} signal{'' if len(signals) == 1 else 's'}"
    body = (
        render_signals(signals)
        if verdict is not None
        else f'<p class="empty">{esc(NO_CLAIMS)}</p>'
    )
    return join(
        [
            "<section>",
            f'<h2>Every claim, with its source<span class="tally">{esc(tally)}</span></h2>',
            f'<p class="lede">{esc(CLAIMS_LEDE)}</p>',
            body,
            "</section>",
        ]
    )


def trace_section(result: AssessmentResult) -> str:
    return join(
        [
            "<section>",
            f"<h2>The trace{trace_tally(result.trace)}</h2>",
            f'<p class="lede">{esc(TRACE_LEDE)}</p>',
            render_stages(result.stages),
            render_trace(result.trace),
            envelope_facts(result),
            "</section>",
        ]
    )


def skipped_section(result: AssessmentResult) -> str:
    count = len(result.skipped)
    tally = f'<span class="tally">{count} skipped</span>' if count else ""
    return join(
        [
            "<section>",
            f"<h2>Stages not run{tally}</h2>",
            f'<p class="lede">{esc(SKIPPED_LEDE)}</p>',
            render_skipped(result.skipped),
            render_errors(result.errors),
            "</section>",
        ]
    )


def render_dossier(result: AssessmentResult) -> str:
    """The whole page for one finished run, complete or partial."""
    body = join(
        [
            '<main class="sheet">',
            masthead(result),
            render_verdict(result),
            claims_section(result),
            trace_section(result),
            skipped_section(result),
            f"<footer>{esc(FOOTNOTE)}</footer>",
            "</main>",
        ]
    )
    return page(f"{BRAND} · {result.run_id}", DOSSIER_CSS, body)


__all__ = [
    "BRAND",
    "claims_section",
    "envelope_facts",
    "masthead",
    "render_dossier",
    "scalar",
    "skipped_section",
    "trace_section",
]
