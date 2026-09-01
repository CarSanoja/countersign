"""Bearer-token protection for the dossier surface, configured only from the environment.

The failure worth designing against is the quiet one: a service that comes up with
no token set and hands vendor files — bank details included — to anyone who reaches
the URL. So an absent `COUNTERSIGN_API_TOKEN` is not read as "auth is off". The
process still starts, `/healthz` still answers so the platform can see the container
is alive, and the dossier routes answer 503 naming the variable they are waiting on.
Closed and diagnosable beats open and silent.

The comparison is constant time because the alternative leaks the secret one byte
at a time to anyone willing to measure.
"""

import os
import secrets
from typing import Annotated, Final

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

API_TOKEN_ENV: Final[str] = "COUNTERSIGN_API_TOKEN"

UNCONFIGURED_DETAIL: Final[str] = (
    f"{API_TOKEN_ENV} is unset, so the dossier routes are closed. Set it from Secret "
    "Manager and restart before serving traffic."
)
UNAUTHORIZED_DETAIL: Final[str] = "A bearer token is required to read a dossier."

bearer_scheme = HTTPBearer(auto_error=False, description="COUNTERSIGN_API_TOKEN")


def configured_token() -> str | None:
    """The deployed secret, or None when the variable is absent or only whitespace.

    Stripped because a secret piped out of Secret Manager arrives with a trailing
    newline more often than not, and a token that fails only in production is worse
    than one that never worked.
    """
    return (os.environ.get(API_TOKEN_ENV) or "").strip() or None


def token_matches(presented: str, expected: str) -> bool:
    """Constant time, so a wrong guess costs the same whatever its first byte."""
    return secrets.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def unconfigured_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=UNCONFIGURED_DETAIL
    )


def unauthorized_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=UNAUTHORIZED_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> None:
    """Guard every dossier route. Misconfiguration is 503; a bad token is 401.

    The two are kept apart on purpose: an operator reading 503 knows the deployment
    is incomplete, and a caller reading 401 knows the deployment is fine and their
    credential is not.
    """
    expected = configured_token()
    if expected is None:
        raise unconfigured_error()
    if credentials is None:
        raise unauthorized_error()
    if not token_matches(credentials.credentials.strip(), expected):
        raise unauthorized_error()


__all__ = [
    "API_TOKEN_ENV",
    "UNAUTHORIZED_DETAIL",
    "UNCONFIGURED_DETAIL",
    "bearer_scheme",
    "configured_token",
    "require_bearer_token",
    "token_matches",
    "unauthorized_error",
    "unconfigured_error",
]
