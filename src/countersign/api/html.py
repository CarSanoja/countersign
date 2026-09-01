"""Server-side HTML with no framework and no CDN, so escaping is ours to get right.

Every value that reaches the page passes through `esc`. Locators come from
search results and from documents, which is to say from outside, so a locator
that is not plainly an http(s) URL is printed as text and never linked.
"""

from collections.abc import Iterable
from html import escape

LINK_SCHEMES = ("https://", "http://")
DOMAIN_STOPS = (" ", "/", "\\", "?", "#", "@", ":", "<", ">", '"')


def esc(value: object) -> str:
    """Escape for both text nodes and quoted attribute values."""
    return escape(str(value), quote=True)


def looks_like_domain(locator: str) -> bool:
    stripped = locator.strip()
    if "." not in stripped or stripped.startswith(".") or stripped.endswith("."):
        return False
    if any(stop in stripped for stop in DOMAIN_STOPS):
        return False
    return stripped.rpartition(".")[2].isalpha()


def href_for(locator: str) -> str | None:
    """The address to link, or None when the locator is not a web address."""
    stripped = locator.strip()
    if stripped.lower().startswith(LINK_SCHEMES):
        return stripped
    if looks_like_domain(stripped):
        return f"https://{stripped}"
    return None


def link(locator: str, extra_class: str = "") -> str:
    """A linked source when it can be linked, monospaced text when it cannot."""
    target = href_for(locator)
    classes = f"locator {extra_class}".strip()
    if target is None:
        return f'<code class="{esc(classes)}">{esc(locator)}</code>'
    return (
        f'<a class="{esc(classes)}" href="{esc(target)}" '
        f'rel="noreferrer noopener" target="_blank">{esc(locator)}</a>'
    )


def join(parts: Iterable[str]) -> str:
    return "\n".join(part for part in parts if part)


def page(title: str, style: str, body: str) -> str:
    """The whole document. One stylesheet, inline, no external request at all."""
    return join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc(title)}</title>",
            f"<style>{style}</style>",
            "</head>",
            "<body>",
            body,
            "</body>",
            "</html>",
        ]
    )


__all__ = ["esc", "href_for", "join", "link", "looks_like_domain", "page"]
