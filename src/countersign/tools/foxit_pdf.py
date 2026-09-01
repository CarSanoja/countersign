"""Foxit PDF Services generation for COUNTERSIGN. Capability: ``doc.generate``.

The out-of-band verification document is the point of the generation stage:
when the verdict is not clear, a person calls the supplier back on a number
nobody in the thread supplied, and reads it off this sheet, which comes from
structured data and an operator's template, not prose. That is all it does.

Two things about this API shape the layer. Auth is ``client_id`` and
``client_secret`` headers, not the Bearer token the eSign product wants, so the
two Foxit credentials never fall back to one another. And conversion is async
behind a task id: the live service answers ``IN_PROGRESS`` where the published
docs promise ``PROCESSING``, so any status but the two terminal ones is running.

Merged values are HTML-escaped: the template is trusted operator work, but the
data came from a document a counterparty sent, and a sheet rendering markup a
supplier chose lets that supplier rewrite the callback number printed on it.
"""

import asyncio
import html
import os
import re
from pathlib import Path
from typing import Any, Final

import httpx
from autocurricula.tools.base import ToolResult, as_function_tool

CAPABILITY: Final[str] = "doc.generate"
BASE_URL: Final[str] = "https://na1.fusion.foxit.com/pdf-services/api"
ENV_CLIENT_ID: Final[str] = "FOXIT_PDF_CLIENT_ID"
ENV_CLIENT_SECRET: Final[str] = "FOXIT_PDF_CLIENT_SECRET"

UPLOAD_TIMEOUT_SECONDS: Final[float] = 60.0
TASK_TIMEOUT_SECONDS: Final[float] = 30.0
POLL_INTERVAL_SECONDS: Final[float] = 1.5
POLL_ATTEMPTS: Final[int] = 40
ERROR_BODY_CHARS: Final[int] = 400

PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
PAGE_CONFIG: Final[dict[str, Any]] = {
    "dimension": {"width": 612, "height": 792}, "rotation": "NONE",
    "pageMode": "MULTIPLE_PAGE", "scalingMode": "SCALE",
}


class MissingCredential(Exception):
    def __init__(self, variable: str) -> None:
        self.variable = variable
        super().__init__(
            f"{variable} is unset. Foxit PDF Services authenticates with "
            f"{ENV_CLIENT_ID}/{ENV_CLIENT_SECRET} as client_id and client_secret headers; "
            "the eSign Bearer token is a different product and no substitute."
        )


class FoxitPdfError(Exception):
    """Foxit answered, and the answer was not a document."""


def _headers() -> dict[str, str]:
    values = {}
    for header, variable in (("client_id", ENV_CLIENT_ID), ("client_secret", ENV_CLIENT_SECRET)):
        value = os.environ.get(variable, "").strip()
        if not value:
            raise MissingCredential(variable)
        values[header] = value
    return values


def _as_html(value: Any) -> str:
    """Escaped markup for one merged value; nesting becomes a nested list."""
    if isinstance(value, dict):
        items = (f"<b>{html.escape(str(k))}</b>: {_as_html(v)}" for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        items = (_as_html(item) for item in value)
    elif isinstance(value, bool):
        return "yes" if value else "no"
    else:
        return html.escape("" if value is None else str(value))
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def render_template(template: str, data: dict[str, Any]) -> str:
    """Substitute every ``{{key}}`` from data, or name the keys that had none.

    An unresolved placeholder is refused rather than left on the page: a literal
    ``{{callback}}`` where the number to call belongs is worse than no document.
    """
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in data:
            return _as_html(data[key])
        missing.append(key)
        return ""

    rendered = PLACEHOLDER.sub(substitute, template)
    if missing:
        raise FoxitPdfError(f"template placeholders with no value in data: {sorted(set(missing))}")
    return rendered


async def _call(
    client: httpx.AsyncClient, method: str, path: str, timeout: float, **kwargs: Any
) -> httpx.Response:
    """One authenticated request. Raises unless Foxit accepted it."""
    response = await client.request(
        method, f"{BASE_URL}{path}", headers=_headers(), timeout=timeout, **kwargs
    )
    if response.status_code >= 400:
        raise FoxitPdfError(f"HTTP {response.status_code}: {response.text[:ERROR_BODY_CHARS]}")
    return response


def _identifier(response: httpx.Response, key: str) -> str:
    try:
        body = response.json()
    except ValueError:
        raise FoxitPdfError(f"HTTP {response.status_code}, non-JSON body") from None
    value = body.get(key) if isinstance(body, dict) else None
    if not isinstance(value, str) or not value:
        raise FoxitPdfError(f"no {key} in the response body")
    return value


async def _converted_document_id(client: httpx.AsyncClient, source_id: str) -> str:
    """Start the HTML conversion and wait for its task to settle."""
    started = await _call(
        client, "POST", "/documents/create/pdf-from-html", TASK_TIMEOUT_SECONDS,
        json={"documentId": source_id, "config": PAGE_CONFIG},
    )
    task_id = _identifier(started, "taskId")
    for _ in range(POLL_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        polled = await _call(client, "GET", f"/tasks/{task_id}", TASK_TIMEOUT_SECONDS)
        status = polled.json()
        state = str(status.get("status", "")).upper()
        if state == "COMPLETED":
            return _identifier(polled, "resultDocumentId")
        if state == "FAILED":
            raise FoxitPdfError(f"task {task_id} failed: {status.get('error') or 'no detail'}")
    raise FoxitPdfError(f"task {task_id} was still running after {POLL_ATTEMPTS} polls")


async def _generate(source: str, name: str) -> tuple[str, bytes]:
    async with httpx.AsyncClient() as client:
        uploaded = await _call(
            client, "POST", "/documents/upload", UPLOAD_TIMEOUT_SECONDS,
            files={"file": (f"{name}.html", source.encode("utf-8"), "text/html")},
        )
        document_id = await _converted_document_id(client, _identifier(uploaded, "documentId"))
        downloaded = await _call(
            client, "GET", f"/documents/{document_id}/download", UPLOAD_TIMEOUT_SECONDS,
            params={"filename": name},
        )
    content = downloaded.content
    if not content.startswith(b"%PDF"):
        raise FoxitPdfError(f"download returned {len(content)} bytes, and not a PDF")
    return document_id, content


async def foxit_generate_document(
    template_path: str, data: dict[str, Any], document_name: str, output_path: str = ""
) -> ToolResult:
    """Render an HTML template plus structured data into the out-of-band PDF.

    MUTATES EXTERNAL STATE: uploads the rendered page to Foxit PDF Services,
    debits PDF Services credits, and writes output_path on local disk when one
    is given. Foxit deletes both documents after 24 hours.
    """
    name = document_name.strip() or "verification"
    try:
        template = await asyncio.to_thread(Path(template_path).read_text, encoding="utf-8")
    except OSError as error:
        return ToolResult.failure(f"cannot read template {template_path}: {error}")
    try:
        document_id, content = await _generate(render_template(template, data), name)
        if output_path:
            await asyncio.to_thread(Path(output_path).write_bytes, content)
    except MissingCredential as error:
        return ToolResult.failure(str(error))
    except FoxitPdfError as error:
        return ToolResult.failure(f"foxit pdf services: {error}")
    except httpx.HTTPError as error:
        return ToolResult.failure(f"foxit pdf services unreachable: {error!r}")
    except OSError as error:
        return ToolResult.failure(f"cannot write {output_path}: {error}")
    return ToolResult.success(
        {
            "document_id": document_id, "document_name": f"{name}.pdf",
            "byte_count": len(content), "output_path": output_path,
            "download_url": f"{BASE_URL}/documents/{document_id}/download",
            "provider": "foxit-pdf-services",
        }
    )


GENERATE_DOCUMENT_TOOL = as_function_tool(foxit_generate_document)
