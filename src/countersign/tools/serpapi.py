"""SerpApi tools for the counterparty verifier.

Every function exposed here requires the capability "web.search" and nothing
else, and none of them mutates external state: the eight SerpApi endpoints are
read-only scrapes of a SERP. What they do spend is quota. One credit per
search, three searches per counterparty, 250 credits a month on the free plan,
which is roughly 83 counterparties before the bill starts.

The work is split by responsibility: transport in serpapi_client, response
shapes in serpapi_models, defensive readers in serpapi_parsers, the two SERP
searches in serpapi_search, the Maps two-hop in serpapi_address, and the
unconfirmed corners of the contract in serpapi_unverified.
"""

from autocurricula.tools.base import as_function_tool

from countersign.tools.serpapi_address import serpapi_verify_address
from countersign.tools.serpapi_client import SERPAPI_API_KEY_ENV
from countersign.tools.serpapi_search import serpapi_adverse_media, serpapi_find_official_site
from countersign.tools.serpapi_unverified import (
    serpapi_account_quota,
    serpapi_news_full_coverage,
    serpapi_official_site_via_google_local,
    serpapi_search_date_range,
)

REQUIRED_CAPABILITY = "web.search"

FIND_OFFICIAL_SITE_TOOL = as_function_tool(serpapi_find_official_site)
ADVERSE_MEDIA_TOOL = as_function_tool(serpapi_adverse_media)
VERIFY_ADDRESS_TOOL = as_function_tool(serpapi_verify_address)

SERPAPI_TOOLS = (FIND_OFFICIAL_SITE_TOOL, ADVERSE_MEDIA_TOOL, VERIFY_ADDRESS_TOOL)

__all__ = [
    "ADVERSE_MEDIA_TOOL",
    "FIND_OFFICIAL_SITE_TOOL",
    "REQUIRED_CAPABILITY",
    "SERPAPI_API_KEY_ENV",
    "SERPAPI_TOOLS",
    "VERIFY_ADDRESS_TOOL",
    "serpapi_account_quota",
    "serpapi_adverse_media",
    "serpapi_find_official_site",
    "serpapi_news_full_coverage",
    "serpapi_official_site_via_google_local",
    "serpapi_search_date_range",
    "serpapi_verify_address",
]
