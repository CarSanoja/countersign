"""Credentials, auth and transport for the Foxit eSign REST API.

Two things about this API shape the layer. Errors arrive as HTTP 200 with
``{"result": "error", ...}``, so success is decided on the body and never on
the status code. And the endpoints that dispatch an envelope live on the same
host as the one that prepares it, so the paths that execute are refused here
rather than merely left uncalled.
"""

import os
from typing import Any

import httpx

CAPABILITY = "envelope.prepare"

ENV_ACCESS_TOKEN = "FOXIT_ESIGN_ACCESS_TOKEN"
ENV_CLIENT_ID = "FOXIT_ESIGN_CLIENT_ID"
ENV_CLIENT_SECRET = "FOXIT_ESIGN_CLIENT_SECRET"
ENV_BASE_URL = "FOXIT_ESIGN_BASE_URL"
ENV_API_OWNER_EMAIL = "FOXIT_ESIGN_API_OWNER_EMAIL"

DEFAULT_BASE_URL = "https://na1.foxitesign.foxit.com/api"
TOKEN_TIMEOUT_SECONDS = 20.0
REQUEST_TIMEOUT_SECONDS = 30.0
ERROR_BODY_LIMIT = 400

NEVER_CALLED_PATHS: frozenset[str] = frozenset(
    {
        "/folders/sendDraftFolder",
        "/folders/modifySharedFolder",
        "/embedded/regenerateEmbeddedSigningSession",
        "/folders/signaturereminder",
        "/folders/cancelFolder",
        "/folders/movetorecyclebin",
        "/folders/delete",
    }
)


class MissingCredential(RuntimeError):
    """A required FOXIT_ESIGN_ variable is absent."""


class FoxitError(RuntimeError):
    """Foxit answered, and the answer was not a success."""


def required_env(name: str, hint: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingCredential(f"{name} is not set{hint}")
    return value


def base_url() -> str:
    return (os.environ.get(ENV_BASE_URL, "").strip() or DEFAULT_BASE_URL).rstrip("/")


def _decoded(response: httpx.Response, what: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        body = response.text[:ERROR_BODY_LIMIT]
        raise FoxitError(f"{what}: HTTP {response.status_code}, non-JSON body: {body}") from None
    if not isinstance(payload, dict):
        raise FoxitError(f"{what}: HTTP {response.status_code}, unexpected JSON shape")
    return payload


def _succeeded(response: httpx.Response, what: str) -> dict[str, Any]:
    payload = _decoded(response, what)
    if payload.get("result") != "success":
        detail = payload.get("error_description") or response.text[:ERROR_BODY_LIMIT]
        raise FoxitError(f"{what}: HTTP {response.status_code}, {detail}")
    return payload


async def _bearer_token(client: httpx.AsyncClient, host: str) -> str:
    """Reuses FOXIT_ESIGN_ACCESS_TOKEN when present, otherwise mints one.

    Does not mutate signable state. The minted token is long lived, so an
    operator is expected to store it and skip this exchange.
    """
    cached = os.environ.get(ENV_ACCESS_TOKEN, "").strip()
    if cached:
        return cached
    hint = f" (set it, or set {ENV_ACCESS_TOKEN} to a token already issued)"
    form = {
        "grant_type": "client_credentials",
        "client_id": required_env(ENV_CLIENT_ID, hint),
        "client_secret": required_env(ENV_CLIENT_SECRET, hint),
        "scope": "read-write",
    }
    owner_email = os.environ.get(ENV_API_OWNER_EMAIL, "").strip()
    if owner_email:
        form["emailId"] = owner_email
    response = await client.post(
        f"{host}/oauth2/access_token", data=form, timeout=TOKEN_TIMEOUT_SECONDS
    )
    token = _decoded(response, "foxit esign token").get("access_token")
    if not isinstance(token, str) or not token:
        raise FoxitError(f"foxit esign token: HTTP {response.status_code}, no access_token")
    return token


async def call(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Authenticated request against one eSign path. Raises on any failure."""
    if path in NEVER_CALLED_PATHS:
        raise FoxitError(f"{path} executes an envelope and is outside {CAPABILITY}")
    host = base_url()
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        token = await _bearer_token(client, host)
        response = await client.request(
            method,
            f"{host}{path}",
            json=json_body,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    return _succeeded(response, f"foxit esign {path}")


async def attempt(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Same as ``call`` but returns (payload, error) instead of raising."""
    try:
        return await call(method, path, json_body, params), None
    except (MissingCredential, FoxitError) as error:
        return None, str(error)
    except httpx.HTTPError as error:
        return None, f"foxit esign {path} transport: {type(error).__name__}: {error}"
