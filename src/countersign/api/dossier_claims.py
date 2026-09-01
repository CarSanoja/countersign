"""Claims and their sources. The rule the section exists to enforce is visible.

`Claim` already refuses to construct without a source, so an unsourced claim
cannot arrive through the API. The renderer still checks, and prints the failure
in red on the page rather than dropping the row, because a claim that lost its
provenance somewhere between the schema and the screen is the one bug this
product cannot afford to hide.
"""

from countersign.api.html import esc, join, link
from countersign.schemas.evidence import Claim, PageBox, SourceRef
from countersign.schemas.verdict import RiskSignal

UNSOURCED = "BUG: this claim reached the page with no source. Do not act on it."


def box_text(box: PageBox) -> str:
    """Pages are counted from zero upstream and from one by people."""
    return (
        f"page {box.page + 1} · {box.left:.0%},{box.top:.0%} "
        f"{box.width:.0%}×{box.height:.0%}"
    )


def render_source(source: SourceRef) -> str:
    box = f'<span class="box">{esc(box_text(source.box))}</span>' if source.box else ""
    snippet = (
        f'<p class="snippet">“{esc(source.snippet)}”</p>' if source.snippet else ""
    )
    retrieved = f'<span class="box">retrieved {esc(source.retrieved_at)}</span>'
    return join(
        [
            '<li class="source">',
            f'<span class="provider">{esc(source.provider)}</span>',
            link(source.locator),
            box,
            retrieved,
            snippet,
            "</li>",
        ]
    )


def render_sources(claim: Claim) -> str:
    if not claim.sources:
        return f'<p class="unsourced">{esc(UNSOURCED)}</p>'
    rows = join(render_source(source) for source in claim.sources)
    return f'<ul class="sources">{rows}</ul>'


def render_claim(claim: Claim, heading: str = "") -> str:
    return join(
        [
            '<li class="claim">',
            heading,
            f'<p class="statement">{esc(claim.statement)}</p>',
            render_sources(claim),
            "</li>",
        ]
    )


def signal_heading(signal: RiskSignal) -> str:
    kind = str(signal.kind).replace("_", " ")
    return join(
        [
            '<div class="claim-head">',
            f'<span class="kind">{esc(kind)}</span>',
            f'<span class="weight">weight {signal.weight:.2f} · '
            f"stated confidence {signal.claim.confidence:.2f}</span>",
            "</div>",
        ]
    )


def render_signals(signals: list[RiskSignal]) -> str:
    if not signals:
        return '<p class="empty">No signal fired. The verdict rests on the absence of one.</p>'
    rows = join(render_claim(signal.claim, signal_heading(signal)) for signal in signals)
    return f'<ol class="claims">{rows}</ol>'


__all__ = [
    "UNSOURCED",
    "box_text",
    "render_claim",
    "render_signals",
    "render_source",
    "render_sources",
    "signal_heading",
]
