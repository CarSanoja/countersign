"""The parts of the SerpApi contract that were never confirmed against a live
response, kept as declared gaps rather than as guesses.

Each one names the exact datum that is missing. They raise instead of returning
a ToolResult because a caller reaching them has a wiring problem, not a runtime
failure to record.
"""

from typing import NoReturn


def serpapi_official_site_via_google_local() -> NoReturn:
    """One-call alternative to the two-hop Maps lookup. Not implemented."""
    raise NotImplementedError(
        "engine=google_local returns the official website inside a 'links' hash, but the "
        "literal key names of that hash are undocumented and were never seen in a live "
        "response. Missing datum: one captured google_local response taken with a funded "
        "SERPAPI_API_KEY, confirming whether links.website exists and is always present."
    )


def serpapi_news_full_coverage() -> NoReturn:
    """Google News story grouping by story_token or topic_token. Not implemented."""
    raise NotImplementedError(
        "the google_news response shape for story_token and topic_token is undocumented: no "
        "official example shows whether a nested 'stories' array appears. Missing datum: one "
        "live google_news response using a story_token, taken with a funded SERPAPI_API_KEY."
    )


def serpapi_search_date_range() -> NoReturn:
    """Date-bounded Google search through the tbs parameter. Not implemented."""
    raise NotImplementedError(
        "engine=google restricts by date through the tbs parameter, whose date-range syntax is "
        "not enumerated in the SerpApi markdown documentation. Missing datum: the verified tbs "
        "value format. Adverse media already has a verified time filter, the when: operator of "
        "google_news, so only the google engine is blocked by this."
    )


def serpapi_account_quota() -> NoReturn:
    """Remaining monthly credits from /account.json. Not implemented as a tool."""
    raise NotImplementedError(
        "the /account.json contract is verified and this call would cost no credit, but no tool "
        "name for it exists in countersign.fleet.capabilities.TOOL_CAPABILITY, so the gate would "
        "fail it closed. Missing datum: a declared tool name mapped to a capability."
    )
