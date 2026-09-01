"""Detecting that a document announces new bank details.

Per the FBI's own reporting this is the highest-value indicator in the whole
pipeline: the moment a supplier's account changes is the moment money is
redirected. The document says so in words, so a phrase table settles it and the
model is not asked to notice.
"""

import re

from countersign.agents.document_extractor_layout import DocumentLayout

_PHRASES = (
    r"bank(?:ing)?\s+(?:details?|account)s?\s+(?:has|have)\s+changed",
    r"our\s+bank\s+(?:has\s+)?changed",
    r"new\s+bank(?:ing)?\s+(?:details?|account)",
    r"updated?\s+(?:our\s+)?bank(?:ing)?\s+(?:details?|account)",
    r"change\s+of\s+bank(?:ing)?\s+(?:details?|account)",
    r"remit\s+to\s+(?:our\s+)?new\s+account",
    r"payments?\s+to\s+our\s+previous\s+account",
    r"please\s+note\s+our\s+bank",
)

_PATTERN = re.compile("|".join(_PHRASES), re.IGNORECASE)


def bank_change_span(layout: DocumentLayout) -> tuple[str, str] | None:
    """The span that announces the change, and the phrase that gave it away."""
    for span in layout.spans:
        match = _PATTERN.search(span.text)
        if match is not None:
            return span.span_id, match.group(0)
    return None
