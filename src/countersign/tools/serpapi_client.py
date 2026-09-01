"""Transport for SerpApi: one GET endpoint, the key carried in the query string.

Every SerpApi endpoint is read-only. The only side effect is accounting: each
/search call spends one credit of the monthly quota, so a retry loop here burns
money rather than data. Retries are therefore deliberately absent.

The key travels in the URL, not in a header, so it is redacted out of every
error string before it can reach a log.
"""

import os
from typing import Any

import httpx
from autocurricula.tools.base import ToolResult

SERPAPI_API_KEY_ENV = "SERPAPI_API_KEY"
SERPAPI_BASE_URL_ENV = "SERPAPI_BASE_URL"
DEFAULT_BASE_URL = "https://serpapi.com"
SEARCH_PATH = "/search.json"
ACCOUNT_PATH = "/account.json"
REQUEST_TIMEOUT_SECONDS = 25.0
DEFAULT_COUNTRY = "es"
DEFAULT_LANGUAGE = "es"
DEFAULT_GOOGLE_DOMAIN = "google.es"
MAX_ERROR_BODY_CHARS = 400
KEY_HELP_URL = "https://serpapi.com/manage-api-key"


def _base_url() -> str:
    configured = os.environ.get(SERPAPI_BASE_URL_ENV, "").strip()
    return (configured or DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str | None:
    return os.environ.get(SERPAPI_API_KEY_ENV, "").strip() or None


_EMPTY_RESULT_MARKERS = (
    "hasn't returned any results",
    "has not returned any results",
    "no results found",
    "returned no results",
)


def _is_empty_result(reported: str) -> bool:
    """SerpApi reports "no results" through the error field.

    A search that legitimately finds nothing is an answer, not a failure: for
    adverse media, finding nothing is the good outcome, and treating it as an
    error degrades the stage and skews the verdict.
    """
    lowered = reported.lower()
    return any(marker in lowered for marker in _EMPTY_RESULT_MARKERS)


def _redact(text: str, key: str) -> str:
    return text.replace(key, "[redacted]")


def _query_params(params: dict[str, Any], key: str) -> dict[str, str]:
    supplied = {
        name: str(value)
        for name, value in params.items()
        if value is not None and str(value) != ""
    }
    return supplied | {"api_key": key}


async def serpapi_get(path: str, params: dict[str, Any]) -> ToolResult:
    """Issue one read-only GET against SerpApi and return the parsed document.

    Mutates no external state. Spends one quota credit when path is a search.
    """
    key = _api_key()
    if key is None:
        return ToolResult.failure(
            f"environment variable {SERPAPI_API_KEY_ENV} is not set or is empty; "
            f"a private SerpApi key is required, obtainable at {KEY_HELP_URL}"
        )
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{_base_url()}{path}", params=_query_params(params, key)
            )
    except httpx.HTTPError as error:
        detail = _redact(str(error), key)
        return ToolResult.failure(
            f"serpapi request to {path} failed: {type(error).__name__}: {detail}"
        )
    return _document_from(response, path, key)


def _document_from(response: httpx.Response, path: str, key: str) -> ToolResult:
    body = _redact(response.text, key)[:MAX_ERROR_BODY_CHARS]
    if response.status_code >= 400:
        return ToolResult.failure(
            f"serpapi returned HTTP {response.status_code} for {path}: {body}"
        )
    try:
        document = response.json()
    except ValueError:
        return ToolResult.failure(f"serpapi returned a non-JSON body for {path}: {body}")
    if not isinstance(document, dict):
        return ToolResult.failure(
            f"serpapi returned a {type(document).__name__} for {path}, expected an object"
        )
    reported = document.get("error")
    if isinstance(reported, str) and reported.strip():
        if _is_empty_result(reported):
            return ToolResult.success({"document": {}, "empty": True, "reason": reported})
        return ToolResult.failure(f"serpapi rejected the search: {_redact(reported, key)}")
    return ToolResult.success({"document": document})
