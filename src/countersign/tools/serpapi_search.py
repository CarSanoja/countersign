"""The two SERP searches of a counterparty check: who they claim to be, and
what has been published about them.

Both require the capability "web.search" and neither mutates external state.
Each call spends one SerpApi credit.
"""

import re

from autocurricula.tools.base import ToolResult

from countersign.tools import serpapi_parsers as parse
from countersign.tools.serpapi_client import (
    DEFAULT_COUNTRY,
    DEFAULT_GOOGLE_DOMAIN,
    DEFAULT_LANGUAGE,
    SEARCH_PATH,
    serpapi_get,
)
from countersign.tools.serpapi_models import AdverseMediaEvidence, OfficialSiteEvidence

DEFAULT_WHEN_WINDOW = "2y"
MAX_ORGANIC_RESULTS = 10
MAX_NEWS_RESULTS = 20

WHEN_WINDOW = re.compile(r"\d+[dmy]")
ADVERSE_TERMS = (
    "fraude",
    "fraud",
    "insolvencia",
    "insolvency",
    "concurso de acreedores",
    "demanda",
    "lawsuit",
    "sanción",
    "sanctions",
    "investigación",
)


def quoted_entity(legal_name: str) -> str | None:
    """Strip the quotes out of the name so it can safely become a quoted phrase."""
    cleaned = legal_name.replace('"', " ").strip()
    return cleaned or None


def _adverse_clause() -> str:
    return " OR ".join(f'"{term}"' if " " in term else term for term in ADVERSE_TERMS)


async def serpapi_find_official_site(
    legal_name: str,
    country_code: str = DEFAULT_COUNTRY,
    language: str = DEFAULT_LANGUAGE,
    google_domain: str = DEFAULT_GOOGLE_DOMAIN,
    extra_terms: str = "",
) -> ToolResult:
    """Find the counterparty's official web presence on Google.

    Returns the organic results and the knowledge graph entry when Google
    returns one. Mutates no external state; spends one SerpApi credit.
    """
    entity = quoted_entity(legal_name)
    if entity is None:
        return ToolResult.failure("legal_name is empty, so there is nothing to search for")
    query = f'"{entity}" {extra_terms}'.strip()
    result = await serpapi_get(
        SEARCH_PATH,
        {
            "engine": "google",
            "q": query,
            "gl": country_code,
            "hl": language,
            "google_domain": google_domain,
        },
    )
    if not result.ok:
        return result
    document = result.payload["document"]
    evidence = OfficialSiteEvidence(
        query=query,
        search_id=parse.search_id(document),
        organic_results=parse.organic_results(document, MAX_ORGANIC_RESULTS),
        knowledge_graph=parse.knowledge_graph(document),
    )
    return ToolResult.success(evidence.model_dump(mode="json"))


async def serpapi_adverse_media(
    legal_name: str,
    country_code: str = DEFAULT_COUNTRY,
    language: str = DEFAULT_LANGUAGE,
    when_window: str = DEFAULT_WHEN_WINDOW,
) -> ToolResult:
    """Search Google News for litigation, insolvency and fraud coverage.

    The time filter is the when: operator inside the query, because google_news
    has no date parameter and refuses q alongside any of its tokens. Mutates no
    external state; spends one SerpApi credit.
    """
    entity = quoted_entity(legal_name)
    if entity is None:
        return ToolResult.failure("legal_name is empty, so there is nothing to search for")
    window = when_window.strip()
    if window and not WHEN_WINDOW.fullmatch(window):
        return ToolResult.failure(
            f"when_window {when_window!r} is not a google_news window such as '7d', '6m' or '2y'"
        )
    query = f'"{entity}" ({_adverse_clause()})'
    if window:
        query = f"{query} when:{window}"
    result = await serpapi_get(
        SEARCH_PATH,
        {"engine": "google_news", "q": query, "gl": country_code, "hl": language},
    )
    if not result.ok:
        return result
    document = result.payload["document"]
    evidence = AdverseMediaEvidence(
        query=query,
        when_window=window or None,
        search_id=parse.search_id(document),
        items=parse.news_items(document, MAX_NEWS_RESULTS),
    )
    return ToolResult.success(evidence.model_dump(mode="json"))
