"""Credentials and transport for the Doctavian Documents API.

The gateway demands two independent credentials on every call: an api-key that
names the API, the version and the environment, and a bearer that names the
caller. It validates the api-key first, so a 401 says nothing about the bearer.
"""

import os
from typing import Any, Final

import httpx
from autocurricula.schemas.common import StrictBaseModel

from countersign.tools.doctavian_envelope import (
    DoctavianApiError,
    describe_failure,
    json_body,
    truncated_body,
)

DEFAULT_BASE_URL: Final[str] = "https://api.doctavian.com/v1"
ENV_BASE_URL: Final[str] = "DOCTAVIAN_BASE_URL"
ENV_API_KEY: Final[str] = "DOCTAVIAN_API_KEY"
ENV_ACCESS_TOKEN: Final[str] = "DOCTAVIAN_ACCESS_TOKEN"
ENV_ACCESS_TOKEN_FALLBACK: Final[str] = "DOCTAVIAN_SERVICE_TOKEN"

TEMPLATE_UPLOAD_PATH: Final[str] = "/documents/template/upload"
DATA_UPLOAD_PATH: Final[str] = "/documents/data/upload"
GENERATE_PATH: Final[str] = "/documents/document/generate"
LIST_PATH: Final[str] = "/documents/document/list"

STORAGE_TEMPLATE: Final[str] = "document-template"
STORAGE_DATA: Final[str] = "document-data"
STORAGE_INPUT: Final[str] = "document-input"
DOWNLOAD_STORAGE_TYPES: Final[tuple[str, ...]] = (
    STORAGE_INPUT,
    STORAGE_TEMPLATE,
    STORAGE_DATA,
)

CONNECT_TIMEOUT_SECONDS: Final[float] = 10.0
UPLOAD_TIMEOUT_SECONDS: Final[float] = 60.0
GENERATE_TIMEOUT_SECONDS: Final[float] = 180.0
DOWNLOAD_TIMEOUT_SECONDS: Final[float] = 60.0
MAX_UPLOAD_BYTES: Final[int] = 20 * 1024 * 1024


class DoctavianCredentialError(RuntimeError):
    """A required DOCTAVIAN_* environment variable is absent or empty."""


class DoctavianCredentials(StrictBaseModel):
    base_url: str
    api_key: str
    access_token: str

    def url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def headers(self, storage_type: str = "") -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "x-api-key": self.api_key,
            "X-Origin": "countersign",
        }
        if storage_type:
            headers["X-Storage-Type"] = storage_type
        return headers


def _required_env(name: str, fallback: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if not value and fallback:
        value = os.environ.get(fallback, "").strip()
    if not value:
        hint = f" (or {fallback})" if fallback else ""
        raise DoctavianCredentialError(f"missing environment variable {name}{hint}")
    return value


def load_credentials() -> DoctavianCredentials:
    """Read the Doctavian credentials from the environment.

    Raises DoctavianCredentialError naming the variable that is absent.
    """
    api_key = _required_env(ENV_API_KEY)
    access_token = _required_env(ENV_ACCESS_TOKEN, ENV_ACCESS_TOKEN_FALLBACK)
    base_url = os.environ.get(ENV_BASE_URL, "").strip() or DEFAULT_BASE_URL
    return DoctavianCredentials(
        base_url=base_url, api_key=api_key, access_token=access_token
    )


def timeout(read_seconds: float) -> httpx.Timeout:
    return httpx.Timeout(read_seconds, connect=CONNECT_TIMEOUT_SECONDS)


def _decoded(response: httpx.Response, operation: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise DoctavianApiError(describe_failure(operation, response))
    payload = json_body(response)
    if not payload:
        raise DoctavianApiError(
            f"doctavian {operation} returned a non-json body: {truncated_body(response)}"
        )
    return payload


async def post_multipart(
    client: httpx.AsyncClient,
    credentials: DoctavianCredentials,
    path: str,
    storage_type: str,
    filename: str,
    content: bytes,
    operation: str,
) -> dict[str, Any]:
    """Upload one file. MUTATES EXTERNAL STATE: writes to Doctavian Storage."""
    response = await client.post(
        credentials.url(path),
        headers=credentials.headers(storage_type),
        files={"file": (filename, content, "application/octet-stream")},
        timeout=timeout(UPLOAD_TIMEOUT_SECONDS),
    )
    return _decoded(response, operation)


async def post_json(
    client: httpx.AsyncClient,
    credentials: DoctavianCredentials,
    path: str,
    body: dict[str, Any],
    operation: str,
    read_seconds: float,
) -> dict[str, Any]:
    """MUTATES EXTERNAL STATE: every documented POST in this API writes or bills."""
    response = await client.post(
        credentials.url(path),
        headers=credentials.headers(),
        json=body,
        timeout=timeout(read_seconds),
    )
    return _decoded(response, operation)


async def get_json(
    client: httpx.AsyncClient,
    credentials: DoctavianCredentials,
    path: str,
    operation: str,
) -> dict[str, Any]:
    """Read-only."""
    response = await client.get(
        credentials.url(path),
        headers=credentials.headers(),
        timeout=timeout(DOWNLOAD_TIMEOUT_SECONDS),
    )
    return _decoded(response, operation)


async def get_binary(
    client: httpx.AsyncClient,
    credentials: DoctavianCredentials,
    path: str,
    storage_type: str,
    operation: str,
) -> bytes:
    """Read-only. Returns the raw stored file, not an envelope."""
    response = await client.get(
        credentials.url(path),
        headers=credentials.headers(storage_type),
        timeout=timeout(DOWNLOAD_TIMEOUT_SECONDS),
    )
    if response.status_code >= 400:
        raise DoctavianApiError(describe_failure(operation, response))
    return response.content
