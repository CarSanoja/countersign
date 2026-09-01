"""Screening a supplier document for instructions aimed at the fleet.

An invoice is attacker-controlled input that a model is about to read. Text
placed in it — white on white, in a footer, inside a line item — that tells the
reader to approve the payment is the obvious attack, and it has to be caught
before extraction rather than after.

Deterministic on purpose. Asking a model whether a document is trying to
manipulate a model puts the judgement inside the blast radius.

The patterns are deliberately narrow. "Please approve the invoice by Friday" is
an ordinary thing for a supplier to write, and a screen that fires on it would
be turned off within a week; "mark this invoice as verified" is not something an
invoice says to a person.
"""

import re

from countersign.agents.document_extractor_layout import DocumentLayout

_PATTERNS = (
    (
        r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|earlier|above)\s+instructions?",
        "override",
    ),
    (r"disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above)", "override"),
    (r"you\s+are\s+(?:now\s+)?(?:a|an)\s+\w+\s+(?:assistant|agent|model)", "role-play"),
    (r"system\s*(?:prompt|message)\s*[:>]", "role-play"),
    (
        r"mark\s+(?:this|the)\s+(?:invoice|vendor|document)\s+as\s+"
        r"(?:safe|verified|trusted|low.risk)",
        "instruction",
    ),
    (r"do\s+not\s+(?:flag|report|escalate|review)", "instruction"),
    (r"no\s+(?:further\s+)?verification\s+(?:is\s+)?(?:required|needed)", "instruction"),
    (r"</?(?:system|assistant|instructions?)>", "delimiter"),
)

_COMPILED = tuple((re.compile(pattern, re.IGNORECASE), kind) for pattern, kind in _PATTERNS)


def screen_spans(layout: DocumentLayout) -> list[tuple[str, str, str]]:
    """Every span that reads as an instruction to the reader.

    Returns (span_id, kind, matched phrase) so a person can be shown the exact
    text and where on the page it sits, rather than a boolean.
    """
    found: list[tuple[str, str, str]] = []
    for span in layout.spans:
        for pattern, kind in _COMPILED:
            match = pattern.search(span.text)
            if match is not None:
                found.append((span.span_id, kind, match.group(0)))
                break
    return found
