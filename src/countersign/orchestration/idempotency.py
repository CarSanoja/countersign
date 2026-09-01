"""The same invoice, twice, must not become two signature requests.

A run is identified by the sha256 of the bytes it assessed, so identity follows
content. A rename does not create a new assessment, and a new file dropped under
an old name does not inherit one. Keying on the name would buy deduplication at
the price of occasionally handing one invoice the verdict of another, and the
two failure modes are not symmetric: missing a duplicate costs one envelope out
of the remaining quota, while reusing the wrong verdict can clear a payment to a
fraudster. So when the reference names no readable file there is no key and no
reuse, rather than a fallback to the name.

Reuse does not depend on how bad the earlier verdict was, and HIGH is the case
that most needs it. A retry, a resent mail or a double click on a high-risk
invoice would otherwise put a second "please confirm this bank change" envelope
in front of the same person, which is the pressure the attack is built on. Nor
can re-deriving help: the input is byte-identical by construction, so a second
pass spends four providers to reach the same answer.

What is never reused is silence. A row whose stored verdict is absent or no
longer validates yields no prior run and the document is assessed again. And the
world can move under a stored verdict, so freshness is the caller's call rather
than a hidden timeout: ``reuse=False`` re-checks the world on the same content.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field, ValidationError

from countersign.orchestration.idempotency_store import index_row, newest_row
from countersign.schemas.verdict import Verdict

KEY_ALGORITHM: Final[str] = "sha256"
CHUNK_BYTES: Final[int] = 1 << 20
MILLISECONDS: Final[float] = 1000.0


class UnreadableDocument(Exception):
    """No bytes, no key. Raised rather than falling back to the file name."""

    def __init__(self, reference: str) -> None:
        super().__init__(f"{reference} is not a readable file, so it has no content key")


class PriorRun(StrictBaseModel):
    """An assessment already on file for this exact content, and when it was made."""

    run_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    verdict: Verdict
    recorded_at: str = ""
    record_id: int | None = None

    @property
    def decided_at(self) -> str:
        return self.verdict.decided_at

    @property
    def summary(self) -> str:
        return f"run {self.run_id} ({self.verdict.level.value}, decided {self.decided_at})"


def document_key(path_or_bytes: str | Path | bytes | bytearray) -> str:
    """The identity of a document: the digest of its bytes, never of its name.

    Args:
        path_or_bytes: the document itself, or a path to read it from.

    Returns:
        The algorithm and the digest, as ``sha256:<hex>``.

    Raises:
        UnreadableDocument: when a path was given and its bytes cannot be read.
    """
    digest = hashlib.sha256()
    if isinstance(path_or_bytes, bytes | bytearray):
        digest.update(path_or_bytes)
        return f"{KEY_ALGORITHM}:{digest.hexdigest()}"
    reference = str(path_or_bytes)
    try:
        handle = Path(reference).expanduser().open("rb")
    except (OSError, ValueError) as error:
        raise UnreadableDocument(reference) from error
    with handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return f"{KEY_ALGORITHM}:{digest.hexdigest()}"


def content_key(document_ref: str) -> str:
    """The key of a run's document, or empty when the reference cannot be read.

    An empty key turns duplicate detection off for that run, which is the safe
    direction: the run proceeds and pays for itself rather than adopting an
    assessment that may belong to different bytes.
    """
    try:
        return document_key(document_ref)
    except UnreadableDocument:
        return ""


async def previous_run(
    key: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> PriorRun | None:
    """Find the newest assessment on file for this content key, if there is one.

    A read, and only a read; what to do with the answer is the pipeline's
    decision. Coming back empty always means the same thing to the caller, which
    is that this document has to be assessed again.

    Args:
        key: the content key returned by ``document_key``.
        transport: an httpx transport, so the request shape can be asserted
            against a mock instead of against the live workspace.

    Returns:
        The prior run, or None when this content has no usable assessment on file.
    """
    if not key.strip():
        return None
    row = await newest_row(key, transport)
    return None if row is None else _prior_from(key, row)


def _prior_from(key: str, row: dict[str, Any]) -> PriorRun | None:
    stored = row.get("evidence")
    if not isinstance(stored, dict):
        return None
    try:
        verdict = Verdict.model_validate(stored)
    except ValidationError:
        return None
    run_id = str(row.get("run_id") or verdict.run_id).strip()
    if not run_id:
        return None
    return PriorRun(
        run_id=run_id,
        document_key=key,
        verdict=verdict,
        recorded_at=_recorded_at(row),
        record_id=_record_id(row),
    )


def _recorded_at(row: dict[str, Any]) -> str:
    """Xano stamps ``created_at`` in epoch milliseconds; every other time here is ISO."""
    stamp = row.get("created_at")
    if isinstance(stamp, bool) or not isinstance(stamp, int | float):
        return str(stamp or "")
    return datetime.fromtimestamp(stamp / MILLISECONDS, tz=UTC).isoformat()


def _record_id(row: dict[str, Any]) -> int | None:
    value = row.get("id")
    return None if isinstance(value, bool) or not isinstance(value, int) else value


__all__ = [
    "CHUNK_BYTES",
    "KEY_ALGORITHM",
    "PriorRun",
    "UnreadableDocument",
    "content_key",
    "document_key",
    "index_row",
    "previous_run",
]
