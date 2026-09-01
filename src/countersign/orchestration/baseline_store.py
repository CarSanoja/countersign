"""Reading the vendor file out of Xano, and nothing else.

Split from the comparison deliberately. "What account is this vendor on file
with" is answered by one table read; "does that matter" is answered with no
network at all. Keeping them apart is what lets the signal that decides a payment
be exercised without a credential, and lets this half be exercised against a mock
transport without a verdict in sight.
"""

import os
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

from countersign.agents.document_extractor_fields import normalise
from countersign.tools import xano

FINGERPRINT_FIELD: Final[str] = "bank_fingerprint"
SINCE_FIELD: Final[str] = "bank_since"
NEWEST_ROWS: Final[int] = 100
ERROR_BODY_CHARS: Final[int] = 400
MILLISECONDS: Final[float] = 1000.0


class BaselineUnavailable(RuntimeError):
    """The vendor table could not be read, which is not an empty answer."""


class VendorBaseline(StrictBaseModel):
    """The account a vendor is on file with, as the vendors table holds it."""

    legal_name: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    since: str = Field(min_length=1)
    locator: str = Field(min_length=1)


async def known_bank(
    legal_name: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> VendorBaseline | None:
    """The account this vendor is on file with, or None when we have never seen it.

    Absence is an answer. A supplier whose first invoice this is has no file, and
    that is a different sentence from "the lookup broke", so a read that actually
    broke raises rather than returning the same None.
    """
    name = legal_name.strip()
    if not name:
        return None
    settings = vendor_settings()
    table_id = required_env(xano.VENDOR_TABLE_ENV)
    for row in await _newest_rows(settings, table_id, transport):
        fingerprint = str(row.get(FINGERPRINT_FIELD) or "").strip()
        if not fingerprint or normalise(str(row.get("legal_name") or "")) != normalise(name):
            continue
        return VendorBaseline(
            legal_name=str(row.get("legal_name") or name),
            fingerprint=fingerprint,
            since=_since(row),
            locator=f"{settings.meta_base_url}/workspace/{settings.workspace_id}"
            f"/table/{table_id}/content/{row.get('id', '')}",
        )
    return None


async def _newest_rows(
    settings: xano.XanoSettings, table_id: str, transport: httpx.AsyncBaseTransport | None
) -> list[dict[str, Any]]:
    """One page of vendor rows, newest first.

    Newest first is the semantics as well as the cheap read: the most recent row
    carrying a fingerprint is that vendor's current file. A vendor whose row has
    aged past the page reads as new, which lands on the weak signal rather than on
    an accusation, and that is the right direction for this lookup to be wrong in.
    """
    body = {"page": 1, "per_page": NEWEST_ROWS, "sort": {"id": "desc"}, "search": []}
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
    except httpx.HTTPError as error:
        raise BaselineUnavailable(
            f"xano request failed: {type(error).__name__}: {error}"
        ) from error
    if not 200 <= response.status_code < 300:
        raise BaselineUnavailable(
            f"xano returned HTTP {response.status_code}: {response.text[:ERROR_BODY_CHARS]}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise BaselineUnavailable(f"xano returned a body that is not json: {error}") from error
    items = payload.get("items") if isinstance(payload, dict) else payload
    return [row for row in items or [] if isinstance(row, dict)]


def _since(row: dict[str, Any]) -> str:
    """When this account became the one on file, as a date a person can read.

    Xano stamps created_at in epoch milliseconds, and the explicit column is
    written by the run that first recorded the account, so the row's own birthday
    is the honest fallback rather than the clock of whoever is asking now.
    """
    recorded = str(row.get(SINCE_FIELD) or "").strip()
    if recorded:
        return recorded
    created = row.get("created_at")
    if isinstance(created, int | float):
        return datetime.fromtimestamp(created / MILLISECONDS, tz=UTC).isoformat()
    return str(created or "").strip() or "an unrecorded date"


def required_env(variable: str) -> str:
    value = os.environ.get(variable, "").strip()
    if not value:
        raise xano.MissingCredential(variable)
    return value


def vendor_settings() -> xano.XanoSettings:
    domain = required_env(xano.DOMAIN_ENV).removeprefix("https://").removeprefix("http://")
    return xano.XanoSettings(
        token=required_env(xano.TOKEN_ENV),
        instance_domain=domain.strip("/"),
        workspace_id=required_env(xano.WORKSPACE_ENV),
    )


__all__ = [
    "FINGERPRINT_FIELD",
    "SINCE_FIELD",
    "BaselineUnavailable",
    "VendorBaseline",
    "known_bank",
    "required_env",
    "vendor_settings",
]
