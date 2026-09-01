"""The sender domain, settled by a rule rather than asked of a model.

Everything after the @ of an email address is a domain. Leaving that to a model
meant one benchmark invoice came back with no sender at all, which silently
removed the single most important signal the pipeline has.
"""

import re

from countersign.agents.document_extractor_layout import DocumentLayout, LayoutSpan

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_BARE = re.compile(r"\b((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\b")

_NOT_A_SENDER = frozenset({"example.com", "example.org", "w3.org"})


def _emails(span: LayoutSpan) -> list[str]:
    return [match.group(1).lower() for match in _EMAIL.finditer(span.text)]


def _bare(span: LayoutSpan) -> list[str]:
    return [match.group(1).lower() for match in _BARE.finditer(span.text)]


def sender_domain_from(layout: DocumentLayout) -> tuple[str, str] | None:
    """The most frequently asserted domain in the document, and its span id.

    An email domain beats a bare mention: a logo reading "Name.com" says who the
    document claims to be, while billing@name.net says where it actually came
    from, and the gap between those two is the whole fraud. Bare domains are the
    fallback for documents that carry no address at all.
    """
    for extract in (_emails, _bare):
        tally: dict[str, int] = {}
        first_span: dict[str, str] = {}
        for span in layout.spans:
            for domain in extract(span):
                if domain in _NOT_A_SENDER:
                    continue
                tally[domain] = tally.get(domain, 0) + 1
                first_span.setdefault(domain, span.span_id)
        if tally:
            best = max(tally, key=lambda domain: (tally[domain], -len(domain)))
            return best, first_span[best]
    return None
