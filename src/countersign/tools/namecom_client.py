"""Transport, credentials and the environment split for the name.com Core API.

name.com runs two registries behind identical paths: production at api.name.com
and a sandbox at api.dev.name.com, each with its own account, its own Basic auth
credentials and its own idea of who owns a domain. That split is the reason this
layer exists, so the environment is an argument on every call and never a
module-level default read from the process. A lookalike sweep answered by the
sandbox would report every confusable name as free and invert the fraud signal.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import Any, Final

import httpx

REQUEST_TIMEOUT_SECONDS: Final[float] = 20.0
ERROR_BODY_CHARS: Final[int] = 400
MAX_DOMAINS_PER_CHECK: Final[int] = 50
REQUESTS_PER_SECOND: Final[int] = 20
SECONDS_BETWEEN_REQUESTS: Final[float] = 1.0 / REQUESTS_PER_SECOND


class NamecomEnvironment(StrEnum):
    PRODUCTION = "production"
    SANDBOX = "sandbox"


BASE_URLS: Final[dict[NamecomEnvironment, str]] = {
    NamecomEnvironment.PRODUCTION: "https://api.name.com/core/v1",
    NamecomEnvironment.SANDBOX: "https://api.dev.name.com/core/v1",
}

USERNAME_ENV: Final[dict[NamecomEnvironment, str]] = {
    NamecomEnvironment.PRODUCTION: "NAMECOM_USERNAME",
    NamecomEnvironment.SANDBOX: "NAMECOM_TEST_USERNAME",
}

TOKEN_ENV: Final[dict[NamecomEnvironment, str]] = {
    NamecomEnvironment.PRODUCTION: "NAMECOM_TOKEN",
    NamecomEnvironment.SANDBOX: "NAMECOM_TEST_TOKEN",
}


class MissingCredential(RuntimeError):
    """A required NAMECOM_ variable is absent for the requested environment."""

    def __init__(self, variable: str, environment: "NamecomEnvironment") -> None:
        self.variable = variable
        super().__init__(
            f"{variable} is not set; it holds the name.com {environment.value} "
            "credential, and the production and sandbox accounts are separate: "
            "neither token authenticates against the other host"
        )


class NamecomError(RuntimeError):
    """name.com answered, and the answer was not usable."""


_TEST_TRANSPORT: httpx.AsyncBaseTransport | None = None


@contextmanager
def injected_transport(transport: httpx.AsyncBaseTransport) -> Iterator[None]:
    """Route every request through a supplied transport, for tests only.

    Registration spends real money in production and a real sandbox order in the
    sandbox, so the write path is exercised against httpx.MockTransport here
    rather than against either registry.
    """
    global _TEST_TRANSPORT
    previous = _TEST_TRANSPORT
    _TEST_TRANSPORT = transport
    try:
        yield
    finally:
        _TEST_TRANSPORT = previous


def resolve_environment(value: str) -> NamecomEnvironment:
    """Map a caller-supplied string onto an environment, refusing anything else."""
    try:
        return NamecomEnvironment(value.strip().lower())
    except ValueError:
        allowed = ", ".join(item.value for item in NamecomEnvironment)
        raise NamecomError(
            f"unknown name.com environment {value!r}; expected one of {allowed}"
        ) from None


def base_url(environment: NamecomEnvironment) -> str:
    return BASE_URLS[environment]


def credentials(environment: NamecomEnvironment) -> tuple[str, str]:
    username = os.environ.get(USERNAME_ENV[environment], "").strip()
    if not username:
        raise MissingCredential(USERNAME_ENV[environment], environment)
    token = os.environ.get(TOKEN_ENV[environment], "").strip()
    if not token:
        raise MissingCredential(TOKEN_ENV[environment], environment)
    return username, token


def _decoded(response: httpx.Response, path: str, token: str) -> dict[str, Any]:
    body = response.text.replace(token, "[redacted]")[:ERROR_BODY_CHARS]
    if response.status_code >= 400:
        raise NamecomError(f"name.com {path} returned HTTP {response.status_code}: {body}")
    try:
        document = response.json()
    except ValueError:
        raise NamecomError(f"name.com {path} returned a non-JSON body: {body}") from None
    if not isinstance(document, dict):
        raise NamecomError(
            f"name.com {path} returned a {type(document).__name__}, expected an object"
        )
    return document


async def request(
    environment: NamecomEnvironment,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Issue one authenticated request against the named environment. Raises on failure."""
    username, token = credentials(environment)
    try:
        async with httpx.AsyncClient(
            base_url=base_url(environment),
            timeout=REQUEST_TIMEOUT_SECONDS,
            auth=httpx.BasicAuth(username, token),
            transport=_TEST_TRANSPORT,
        ) as client:
            response = await client.request(method, path, json=json_body, params=params)
    except httpx.HTTPError as error:
        detail = str(error).replace(token, "[redacted]")
        raise NamecomError(
            f"name.com {path} transport failed: {type(error).__name__}: {detail}"
        ) from None
    return _decoded(response, path, token)


async def attempt(
    environment: NamecomEnvironment,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Same as ``request`` but returns (document, error) instead of raising."""
    try:
        return await request(environment, method, path, json_body, params), None
    except (MissingCredential, NamecomError) as error:
        return None, str(error)
