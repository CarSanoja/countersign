"""The Doctavian tool surface. Capability: doc.generate.

Generation is one atomic tool call because Doctavian's Storage is single-use:
the template and the data are deleted by the next generation that consumes them,
whether it succeeds or fails. A tool that only uploaded would hand the agent a
urn that is already dead, so upload, generate and download travel together.

Credentials come from DOCTAVIAN_API_KEY and DOCTAVIAN_ACCESS_TOKEN (falling back
to DOCTAVIAN_SERVICE_TOKEN, which is the name .env.example already carries); the
gateway needs both the api-key and the bearer on every call.

Only doctavian_generate_document is registered as an agent tool. It is the one
name TOOL_CAPABILITY maps to doc.generate, and an unmapped tool fails closed at
the gate, so the credential check stays a plain function the app can call.
"""

from pathlib import Path
from typing import Any

import httpx
from autocurricula.tools.base import ToolResult, as_function_tool
from pydantic import ValidationError

from countersign.tools.doctavian_client import (
    ENV_ACCESS_TOKEN,
    ENV_API_KEY,
    ENV_BASE_URL,
    GENERATE_TIMEOUT_SECONDS,
    LIST_PATH,
    MAX_UPLOAD_BYTES,
    DoctavianCredentialError,
    get_json,
    load_credentials,
    timeout,
)
from countersign.tools.doctavian_document import (
    DEFAULT_LOCALE,
    DEFAULT_TIMEZONE,
    GenerationRequest,
    request_problem,
    template_problem,
)
from countersign.tools.doctavian_envelope import DoctavianApiError
from countersign.tools.doctavian_generation import run_generation

REQUIRED_CAPABILITY = "doc.generate"


async def doctavian_generate_document(
    template_path: str,
    data: dict[str, Any],
    document_name: str,
    file_format: str = "pdf",
    output_path: str = "",
    external_id: str = "",
    locale: str = DEFAULT_LOCALE,
    timezone: str = DEFAULT_TIMEZONE,
) -> ToolResult:
    """Render a template plus a data payload into a document and return its storage id.

    MUTATES EXTERNAL STATE: uploads the template and the data to Doctavian Storage,
    which consumes and deletes both; bills the generation against the subscription;
    and writes output_path on local disk when one is given. Capability doc.generate.

    Args:
        template_path: local .docx or .xlsx template to render.
        data: the JSON payload the template merges.
        document_name: name of the output, without extension.
        file_format: pdf, docx or xlsx.
        output_path: local path to save the generated file; empty skips the download.
        external_id: optional id echoed back in externalContext for traceability.
        locale: document locale, in the short form the official walkthrough uses.
        timezone: IANA zone the document renders its dates in.

    Returns:
        ToolResult whose payload is a GeneratedDocument.
    """
    template = Path(template_path)
    try:
        request = GenerationRequest(
            document_name=document_name,
            file_format=file_format,
            output_path=output_path,
            external_id=external_id,
            locale=locale,
            timezone=timezone,
        )
    except ValidationError as error:
        return ToolResult.failure(f"invalid doctavian generation request: {error}")
    problem = template_problem(template) or request_problem(request)
    if problem:
        return ToolResult.failure(problem)
    try:
        credentials = load_credentials()
        template_bytes = template.read_bytes()
        if len(template_bytes) > MAX_UPLOAD_BYTES:
            return ToolResult.failure(
                f"template {template.name} is {len(template_bytes)} bytes, over the "
                f"{MAX_UPLOAD_BYTES} byte gateway limit"
            )
        document = await run_generation(
            credentials, template, template_bytes, data, request
        )
    except DoctavianCredentialError as error:
        return ToolResult.failure(str(error))
    except DoctavianApiError as error:
        return ToolResult.failure(str(error))
    except httpx.HTTPError as error:
        return ToolResult.failure(f"doctavian transport failure: {type(error).__name__}: {error}")
    except OSError as error:
        return ToolResult.failure(f"doctavian could not read or write a local file: {error}")
    return ToolResult.success(document.model_dump(mode="json"))


async def doctavian_check_credentials() -> ToolResult:
    """Smoke-test the credentials against the document list. Reads only, mutates nothing.

    This is the call the official quickstart uses to prove a key and a token work
    together, and it is what decides whether this provider runs live or on fixtures.

    Returns:
        ToolResult carrying the base url that answered and the operation id.
    """
    try:
        credentials = load_credentials()
        async with httpx.AsyncClient(timeout=timeout(GENERATE_TIMEOUT_SECONDS)) as client:
            payload = await get_json(client, credentials, LIST_PATH, "list")
    except DoctavianCredentialError as error:
        return ToolResult.failure(str(error))
    except DoctavianApiError as error:
        return ToolResult.failure(str(error))
    except httpx.HTTPError as error:
        return ToolResult.failure(f"doctavian transport failure: {type(error).__name__}: {error}")
    return ToolResult.success(
        {"base_url": credentials.base_url, "operation_id": str(payload.get("operationId", ""))}
    )


def fetch_access_token(provider: str) -> str:
    """Not implemented: the OAuth parameters are unpublished."""
    raise NotImplementedError(
        f"cannot mint a bearer for provider {provider!r}: POST /public/v1/auth/{{provider}}/token "
        "carries an empty schema in the OpenAPI spec, so client_id, scopes, redirect_uri, "
        "grant_type and the response field names are all unknown. Copy the access token from "
        "https://portal.doctavian.com and set DOCTAVIAN_ACCESS_TOKEN."
    )


def generate_document_async(body: dict[str, Any]) -> str:
    """Not implemented: the async path needs a key agreed out of band."""
    raise NotImplementedError(
        "POST /v1/documents/document/generate/async requires the x-client-authorization "
        "header: a JWT encrypted with a 16-byte AES key and 16-byte IV that Doctavian agrees "
        "out of band. Neither the key, the IV, nor the callback payload schema are published, "
        "and POST /v1/common/client/token is absent from the OpenAPI spec. "
        f"body keys offered: {sorted(body)}"
    )


GENERATE_DOCUMENT_TOOL = as_function_tool(doctavian_generate_document)

DOCTAVIAN_TOOLS = (GENERATE_DOCUMENT_TOOL,)

__all__ = [
    "DOCTAVIAN_TOOLS",
    "ENV_ACCESS_TOKEN",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "GENERATE_DOCUMENT_TOOL",
    "REQUIRED_CAPABILITY",
    "doctavian_check_credentials",
    "doctavian_generate_document",
    "fetch_access_token",
    "generate_document_async",
]
