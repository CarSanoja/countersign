"""Xano Metadata API: the only durable state COUNTERSIGN writes.

Capability: backend.persist. The vendor table holds mutable workflow state; the
audit table is append-only, and since the sole enforcement of that is the token
scope, no update or delete against it is exposed here.
"""

import os
from typing import Any, Final

import httpx
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.tools.base import ToolResult, as_function_tool
from pydantic import Field, ValidationError

ACCOUNT_META_BASE_URL: Final[str] = "https://app.xano.com/api:meta"
REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
RATE_LIMITED_STATUS: Final[int] = 429
ERROR_BODY_CHARS: Final[int] = 400

TOKEN_ENV: Final[str] = "XANO_TOKEN"
DOMAIN_ENV: Final[str] = "XANO_INSTANCE_DOMAIN"
WORKSPACE_ENV: Final[str] = "XANO_WORKSPACE_ID"
VENDOR_TABLE_ENV: Final[str] = "XANO_VENDOR_TABLE_ID"
AUDIT_TABLE_ENV: Final[str] = "XANO_AUDIT_TABLE_ID"


class MissingCredential(Exception):
    def __init__(self, variable: str) -> None:
        super().__init__(f"missing environment variable {variable}")


class XanoSettings(StrictBaseModel):
    token: str
    instance_domain: str
    workspace_id: str

    @property
    def meta_base_url(self) -> str:
        return f"https://{self.instance_domain}/api:meta"


class AuditEvent(StrictBaseModel):
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


def _required_env(variable: str) -> str:
    value = os.environ.get(variable, "").strip()
    if not value:
        raise MissingCredential(variable)
    return value


def _load_settings() -> XanoSettings:
    domain = _required_env(DOMAIN_ENV).removeprefix("https://").removeprefix("http://")
    return XanoSettings(
        token=_required_env(TOKEN_ENV),
        instance_domain=domain.strip("/"),
        workspace_id=_required_env(WORKSPACE_ENV),
    )


def _decode(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _result_from_response(response: httpx.Response) -> ToolResult:
    body = response.text[:ERROR_BODY_CHARS]
    if response.status_code == RATE_LIMITED_STATUS:
        return ToolResult.failure(f"xano rate limited (HTTP 429): {body}")
    if not 200 <= response.status_code < 300:
        return ToolResult.failure(f"xano returned HTTP {response.status_code}: {body}")
    return ToolResult.success({"data": _decode(response)})


async def _meta_request(
    settings: XanoSettings, method: str, path: str, json_body: Any | None = None
) -> ToolResult:
    headers = {"Authorization": f"Bearer {settings.token}"}
    try:
        async with httpx.AsyncClient(
            base_url=settings.meta_base_url, timeout=REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.request(method, path, json=json_body, headers=headers)
    except httpx.HTTPError as error:
        return ToolResult.failure(f"xano request failed: {type(error).__name__}: {error}")
    return _result_from_response(response)


async def xano_persist_vendor(vendor: dict[str, Any], content_id: str = "") -> ToolResult:
    """Persist the vendor record. MUTATES external state.

    Args:
        vendor: the row as the vendor table declares it, no envelope.
        content_id: when given, replaces that row instead of inserting a new one.

    Returns:
        ToolResult whose payload data holds the record Xano echoed back.
    """
    if not vendor:
        return ToolResult.failure("vendor record is empty; nothing to persist")
    try:
        settings = _load_settings()
        table_id = _required_env(VENDOR_TABLE_ENV)
    except MissingCredential as error:
        return ToolResult.failure(str(error))
    base = f"/workspace/{settings.workspace_id}/table/{table_id}/content"
    if content_id:
        return await _meta_request(settings, "PUT", f"{base}/{content_id}", json_body=vendor)
    return await _meta_request(settings, "POST", base, json_body=vendor)


async def xano_append_audit(events: list[dict[str, Any]]) -> ToolResult:
    """Append entries to the audit table in one request. MUTATES external state.

    Bulk is not an optimisation: the free tier allows ten requests per twenty
    seconds, so a row-by-row loop locks the pipeline out.

    Args:
        events: entries carrying actor, action, entity_id and an optional payload.

    Returns:
        ToolResult whose payload data holds the ids Xano assigned, in order.
    """
    if not events:
        return ToolResult.failure("no audit events to append")
    try:
        items = [AuditEvent(**event).model_dump(mode="json") for event in events]
    except (ValidationError, TypeError) as error:
        return ToolResult.failure(f"invalid audit event: {error}")
    try:
        settings = _load_settings()
        table_id = _required_env(AUDIT_TABLE_ENV)
    except MissingCredential as error:
        return ToolResult.failure(str(error))
    return await _meta_request(
        settings,
        "POST",
        f"/workspace/{settings.workspace_id}/table/{table_id}/content/bulk",
        json_body={"items": items, "allow_id_field": False},
    )


async def read_audit_page(page: int = 1, per_page: int = 50) -> ToolResult:
    """Read one page of the audit table, newest first. Does not mutate.

    A POST, but the scope it consumes is Workspace Content read.
    """
    try:
        settings = _load_settings()
        table_id = _required_env(AUDIT_TABLE_ENV)
    except MissingCredential as error:
        return ToolResult.failure(str(error))
    return await _meta_request(
        settings,
        "POST",
        f"/workspace/{settings.workspace_id}/table/{table_id}/content/search",
        json_body={"page": page, "per_page": per_page, "sort": {"id": "desc"}, "search": []},
    )


async def discover_instance_domain() -> ToolResult:
    """Resolve the real instance host from the account API. Does not mutate.

    The published spec advertises a placeholder host, so the domain is read, not assumed.
    """
    try:
        token = _required_env(TOKEN_ENV)
    except MissingCredential as error:
        return ToolResult.failure(str(error))
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{ACCOUNT_META_BASE_URL}/instance", headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.HTTPError as error:
        return ToolResult.failure(f"xano request failed: {type(error).__name__}: {error}")
    return _result_from_response(response)


def push_workspace_multidoc(xanoscript: str) -> ToolResult:
    """Apply a whole workspace definition. Left unimplemented on purpose."""
    raise NotImplementedError(
        "POST /workspace/{id}/multidoc is not wired: the spec declares only the branch query "
        "parameter while the prose adds partial, delete, env, records, truncate, as_draft, "
        "transaction and force, unreconciled against a live server. Needed to implement it: a "
        "throwaway Xano workspace and a XANO_TOKEN with Workspace Database create and update "
        "scopes, to confirm which flags are accepted before a destructive call."
    )


def build_xano_tools() -> list[Any]:
    return [as_function_tool(xano_persist_vendor), as_function_tool(xano_append_audit)]
