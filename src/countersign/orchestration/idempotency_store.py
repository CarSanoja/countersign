"""Where the reuse index lives: a vendors row addressed by the bytes it assessed.

The index is a row rather than a table of its own because the workspace has the
two tables the fleet created and the reuse question is about a vendor
assessment, not about a new entity. What makes a row an index entry is the
``document_key`` column: it is written only by a run that actually spent the
providers, so a run that merely quoted an earlier verdict leaves its own record
without becoming the answer to the next lookup.

The query is a content search and nothing else. This module can read the index
and write one row into it; it holds no path that could rewrite or remove one.
"""

import os
from typing import Any, Final

import httpx

from countersign.schemas.verdict import Verdict
from countersign.tools import xano

NEWEST_FIRST: Final[dict[str, str]] = {"id": "desc"}


def index_row(
    key: str,
    run_id: str,
    document_ref: str,
    verdict: Verdict,
    *,
    legal_name: str = "",
    official_domain: str = "",
) -> dict[str, Any]:
    """The vendors row that makes this content findable by the next run.

    The verdict travels whole in ``evidence`` rather than as a level and a
    headline, because a reused HIGH has to arrive carrying the signals it was
    grounded in. Storing the level alone would launder an evidenced verdict into
    a bare assertion, which is the one thing the verdict model refuses to be.
    """
    return {
        "document_key": key,
        "run_id": run_id,
        "document_ref": document_ref,
        "legal_name": legal_name,
        "official_domain": official_domain,
        "claimed_domain": "",
        "verdict": verdict.level.value,
        "risk_level": verdict.level.value,
        "risk_score": round(verdict.score, 2),
        "headline": verdict.headline,
        "recommended_action": verdict.recommended_action,
        "decided_at": verdict.decided_at,
        "assessed_at": verdict.decided_at,
        "evidence": verdict.model_dump(mode="json"),
    }


async def newest_row(
    key: str, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any] | None:
    """The most recent vendors row carrying this content key, or None.

    Every way of failing returns None, because to the caller an unconfigured
    workspace, a refused request and a table with no such row all mean the same
    thing: this document has no assessment on file that can be trusted.
    """
    try:
        settings = _settings()
        table_id = _required(xano.VENDOR_TABLE_ENV)
    except xano.MissingCredential:
        return None
    body = {"page": 1, "per_page": 1, "sort": NEWEST_FIRST, "search": {"document_key": key}}
    path = f"/workspace/{settings.workspace_id}/table/{table_id}/content/search"
    try:
        async with httpx.AsyncClient(
            base_url=settings.meta_base_url,
            timeout=xano.REQUEST_TIMEOUT_SECONDS,
            transport=transport,
        ) as client:
            response = await client.post(
                path, json=body, headers={"Authorization": f"Bearer {settings.token}"}
            )
    except httpx.HTTPError:
        return None
    return _first_item(response)


def _first_item(response: httpx.Response) -> dict[str, Any] | None:
    if not 200 <= response.status_code < 300:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    return items[0]


def _settings() -> xano.XanoSettings:
    domain = _required(xano.DOMAIN_ENV).removeprefix("https://").removeprefix("http://")
    return xano.XanoSettings(
        token=_required(xano.TOKEN_ENV),
        instance_domain=domain.strip("/"),
        workspace_id=_required(xano.WORKSPACE_ENV),
    )


def _required(variable: str) -> str:
    value = os.environ.get(variable, "").strip()
    if not value:
        raise xano.MissingCredential(variable)
    return value


__all__ = ["NEWEST_FIRST", "index_row", "newest_row"]
