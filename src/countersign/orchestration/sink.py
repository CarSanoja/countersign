"""Where the trace goes to survive the process.

Xano's free tier allows ten requests per twenty seconds, and one run produces a
row per gate decision, so the default writes the whole trace in a single bulk
request. The row-at-a-time path against /content is kept for the case where the
bulk endpoint is unavailable, and it paces itself under that ceiling.

Credentials are read through the names ``countersign.tools.xano`` declares, so
there is one place in the codebase that knows what a Xano credential is called.
"""

import asyncio
import os
from typing import Any, Protocol

import httpx
from autocurricula.tools.base import ToolResult

from countersign.tools import xano

BULK_SUFFIX = "/bulk"
SECONDS_BETWEEN_WRITES = 2.0
ERROR_BODY_CHARS = 400


class TraceSink(Protocol):
    """Anything that can take the run's audit rows and be responsible for them."""

    async def write(self, rows: list[dict[str, Any]]) -> ToolResult: ...


class MemoryTraceSink:
    """Keeps the rows in the process. The sink a test injects."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def write(self, rows: list[dict[str, Any]]) -> ToolResult:
        self.rows.extend(rows)
        return ToolResult.success({"written": len(rows), "sink": "memory"})


class XanoTraceSink:
    """Appends the trace to the audit_log table of the configured workspace.

    ``transport`` exists so the request shape can be asserted against a
    MockTransport instead of against the live workspace.
    """

    def __init__(
        self,
        *,
        bulk: bool = True,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.bulk = bulk
        self.timeout = timeout if timeout is not None else xano.REQUEST_TIMEOUT_SECONDS
        self.transport = transport

    async def write(self, rows: list[dict[str, Any]]) -> ToolResult:
        if not rows:
            return ToolResult.failure("there is no trace to persist")
        try:
            settings = _settings()
            table_id = _required(xano.AUDIT_TABLE_ENV)
        except xano.MissingCredential as error:
            return ToolResult.failure(str(error))
        path = f"/workspace/{settings.workspace_id}/table/{table_id}/content"
        async with httpx.AsyncClient(
            base_url=settings.meta_base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            headers = {"Authorization": f"Bearer {settings.token}"}
            if self.bulk:
                return await _post_bulk(client, headers, path, rows)
            return await _post_each(client, headers, path, rows)


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


async def _post_bulk(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    path: str,
    rows: list[dict[str, Any]],
) -> ToolResult:
    body = {"items": rows, "allow_id_field": False}
    result = await _send(client, headers, f"{path}{BULK_SUFFIX}", body)
    if not result.ok:
        return result
    return ToolResult.success({"written": len(rows), "sink": "xano", "mode": "bulk"})


async def _post_each(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    path: str,
    rows: list[dict[str, Any]],
) -> ToolResult:
    written = 0
    for index, row in enumerate(rows):
        if index:
            await asyncio.sleep(SECONDS_BETWEEN_WRITES)
        result = await _send(client, headers, path, row)
        if not result.ok:
            return ToolResult.failure(f"{result.error} (after {written} of {len(rows)} rows)")
        written += 1
    return ToolResult.success({"written": written, "sink": "xano", "mode": "content"})


async def _send(
    client: httpx.AsyncClient, headers: dict[str, str], path: str, body: Any
) -> ToolResult:
    try:
        response = await client.post(path, json=body, headers=headers)
    except httpx.HTTPError as error:
        return ToolResult.failure(f"xano request failed: {type(error).__name__}: {error}")
    if not 200 <= response.status_code < 300:
        return ToolResult.failure(
            f"xano returned HTTP {response.status_code}: {response.text[:ERROR_BODY_CHARS]}"
        )
    return ToolResult.success({})


__all__ = ["MemoryTraceSink", "TraceSink", "XanoTraceSink"]
