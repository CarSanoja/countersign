"""Reading what Doctavian answers.

Two different envelopes come back from the same API: the gateway wraps upload
failures one way and the generate endpoint wraps its own another, adding
externalContext and userId alongside the error. They agree on where the useful
codes sit, and that agreement is the only thing this module relies on.
"""

from typing import Any, Final

import httpx

ERROR_BODY_CHARS: Final[int] = 400


class DoctavianApiError(RuntimeError):
    """Doctavian rejected the call or answered something this module cannot read."""


def truncated_body(response: httpx.Response) -> str:
    collapsed = " ".join(response.text.split())
    return collapsed[:ERROR_BODY_CHARS] if collapsed else "<empty body>"


def json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def describe_failure(operation: str, response: httpx.Response) -> str:
    """Render either error envelope as one line.

    Both nest their codes under error.innerErrors, and operationId is the handle
    Doctavian support asks for when a generation fails opaquely.
    """
    payload = json_body(response)
    error = payload.get("error")
    inner = error.get("innerErrors") if isinstance(error, dict) else None
    codes = [
        f"{item.get('code', 'UNKNOWN')}: {item.get('message', '')}".strip()
        for item in inner or []
        if isinstance(item, dict)
    ]
    detail = " | ".join(codes) if codes else truncated_body(response)
    operation_id = payload.get("operationId")
    trace = f" operationId={operation_id}" if operation_id else ""
    return f"doctavian {operation} failed: HTTP {response.status_code} {detail}{trace}"


def envelope_data(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    data = result.get("data") if isinstance(result, dict) else None
    return data if isinstance(data, dict) else {}


def first_uploaded_id(payload: dict[str, Any], operation: str) -> str:
    files = envelope_data(payload).get("files")
    entry = files[0] if isinstance(files, list) and files else None
    identifier = entry.get("id") if isinstance(entry, dict) else None
    if not isinstance(identifier, str) or not identifier:
        raise DoctavianApiError(
            f"doctavian {operation} returned no file id: {str(payload)[:ERROR_BODY_CHARS]}"
        )
    return identifier


def storage_id(urn: str) -> str:
    """The generated urn is a bare guid in one official source and '<guid>:<name>'
    in the other, while the download path is declared as a uuid."""
    return urn.split(":", 1)[0].strip()


def consumption(payload: dict[str, Any]) -> dict[str, float]:
    """The billed dimensions of a generation, flattened to dimension -> value."""
    entries = payload.get("consumption")
    if not isinstance(entries, list):
        return {}
    return {
        str(entry["dimension"]): float(entry.get("value", 0))
        for entry in entries
        if isinstance(entry, dict) and "dimension" in entry
    }
