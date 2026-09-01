"""HTTP transport for Nutrient DWS: two products, two keys, one host.

api.nutrient.io serves the Processor API and the Data Extraction API from the
same origin with separate keys and separate credit pools. A Processor key sent
to /extraction/* answers 401 and reads like a malformed header, so the two
credentials are kept apart here and never fall back to one another.
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Final

import httpx
from autocurricula.tools.base import ToolResult

BASE_URL: Final[str] = "https://api.nutrient.io"
EXTRACTION_KEY_ENV: Final[str] = "NUTRIENT_DATA_EXTRACTION_KEY"
PROCESSOR_KEY_ENV: Final[str] = "NUTRIENT_PROCESSOR_KEY"
DATA_EXTRACTION_API_VERSION: Final[str] = "2026-05-25"
ENGINE_VERSION: Final[str] = "stable"
EXTRACTION_TIMEOUT_SECONDS: Final[float] = 120.0
PROCESSOR_TIMEOUT_SECONDS: Final[float] = 180.0
ACCOUNT_TIMEOUT_SECONDS: Final[float] = 15.0
ERROR_BODY_CHARS: Final[int] = 400


class MissingCredential(Exception):
    def __init__(self, variable: str) -> None:
        self.variable = variable
        super().__init__(
            f"{variable} is unset. The Processor API and the Data Extraction API are "
            "separate products with separate keys and separate credit pools on the same "
            "host; a key for one returns 401 on the other, and NUTRIENT_API_KEY is not a "
            "substitute for either."
        )


class NutrientHttpError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body[:ERROR_BODY_CHARS]
        super().__init__(f"nutrient answered HTTP {status_code}: {self.body}")


class NutrientTransportError(Exception):
    pass


def _bearer(variable: str) -> str:
    value = os.environ.get(variable, "").strip()
    if not value:
        raise MissingCredential(variable)
    return f"Bearer {value}"


def extraction_headers() -> dict[str, str]:
    """Pin the dated contract explicitly: the implicit default is whatever was
    current when the key was created, which differs between keys of one account."""
    return {
        "Authorization": _bearer(EXTRACTION_KEY_ENV),
        "x-nutrient-api-version": DATA_EXTRACTION_API_VERSION,
        "x-nutrient-engine-version": ENGINE_VERSION,
    }


def processor_headers() -> dict[str, str]:
    return {"Authorization": _bearer(PROCESSOR_KEY_ENV)}


async def post_document(
    path: str,
    *,
    headers: dict[str, str],
    part_name: str,
    filename: str,
    content: bytes,
    instructions: str,
    timeout: float,
) -> httpx.Response:
    """Post one multipart request whose file part name is referenced by the
    instructions. Mutates external state: the caller's endpoint debits credits."""
    files = {part_name: (filename, content, "application/pdf")}
    return await _send(
        "POST",
        path,
        headers=headers,
        timeout=timeout,
        files=files,
        data={"instructions": instructions},
    )


async def get_json(path: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
    """Read-only call. Does not mutate external state."""
    return await _send("GET", path, headers=headers, timeout=timeout)


async def _send(
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    timeout: float,
    files: dict[str, tuple[str, bytes, str]] | None = None,
    data: dict[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.request(
                method, f"{BASE_URL}{path}", headers=headers, files=files, data=data
            )
        except httpx.HTTPError as error:
            raise NutrientTransportError(f"{type(error).__name__}: {error}") from error
    if response.status_code >= 400:
        raise NutrientHttpError(response.status_code, _body_excerpt(response))
    return response


def _body_excerpt(response: httpx.Response) -> str:
    try:
        return response.text
    except UnicodeDecodeError:
        return f"<{len(response.content)} bytes of non-text body>"


def failure_from(error: Exception) -> ToolResult:
    """Turn any transport or credential fault into a result the caller can read."""
    if isinstance(error, MissingCredential):
        return ToolResult.failure(str(error))
    if isinstance(error, NutrientHttpError):
        return ToolResult.failure(f"nutrient HTTP {error.status_code}: {error.body}")
    if isinstance(error, NutrientTransportError):
        return ToolResult.failure(f"nutrient unreachable: {error}")
    return ToolResult.failure(f"nutrient call failed: {type(error).__name__}: {error}")


async def read_document(document_path: str) -> bytes | ToolResult:
    """Load a document off disk without blocking the event loop."""
    try:
        return await asyncio.to_thread(Path(document_path).read_bytes)
    except OSError as error:
        return ToolResult.failure(f"cannot read {document_path}: {error}")


async def write_document(output_path: str, content: bytes) -> None:
    """Persist a returned document without blocking the event loop."""
    await asyncio.to_thread(Path(output_path).write_bytes, content)


def response_json(response: httpx.Response) -> dict[str, Any]:
    body = response.json()
    if not isinstance(body, dict):
        raise NutrientHttpError(response.status_code, "expected a JSON object body")
    return body
