"""The generation flow: upload, generate, download.

The three calls belong together because Doctavian deletes the uploaded template
and data as soon as a generation consumes them. Splitting them across tool calls
would hand the agent urns that are already dead.
"""

import json
from pathlib import Path
from typing import Any

import httpx

from countersign.tools.doctavian_client import (
    DATA_UPLOAD_PATH,
    DOWNLOAD_STORAGE_TYPES,
    GENERATE_PATH,
    GENERATE_TIMEOUT_SECONDS,
    STORAGE_DATA,
    STORAGE_TEMPLATE,
    TEMPLATE_UPLOAD_PATH,
    DoctavianCredentials,
    get_binary,
    post_json,
    post_multipart,
    timeout,
)
from countersign.tools.doctavian_document import (
    GeneratedDocument,
    GenerationRequest,
    data_filename,
    generate_body,
    generated_document,
)
from countersign.tools.doctavian_envelope import DoctavianApiError, first_uploaded_id


async def save_document(
    client: httpx.AsyncClient,
    credentials: DoctavianCredentials,
    document: GeneratedDocument,
    destination: Path,
) -> GeneratedDocument:
    """MUTATES local disk.

    The X-Storage-Type a generated document lives under is not published, so the
    documented containers are tried in turn and the one that answered is recorded.
    """
    path = f"/documents/document/{document.storage_id}/download"
    attempts: list[str] = []
    for storage_type in DOWNLOAD_STORAGE_TYPES:
        try:
            content = await get_binary(client, credentials, path, storage_type, "download")
        except DoctavianApiError as error:
            attempts.append(str(error))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return document.model_copy(
            update={"local_path": str(destination), "download_storage_type": storage_type}
        )
    raise DoctavianApiError(
        "doctavian download failed under every documented X-Storage-Type "
        f"({', '.join(DOWNLOAD_STORAGE_TYPES)}); the container a generated document is "
        f"stored under is not published. attempts: {' || '.join(attempts)}"
    )


async def run_generation(
    credentials: DoctavianCredentials,
    template: Path,
    template_bytes: bytes,
    data: dict[str, Any],
    request: GenerationRequest,
) -> GeneratedDocument:
    """MUTATES EXTERNAL STATE: uploads both inputs, bills one generation, and
    writes request.output_path on local disk when it is set."""
    async with httpx.AsyncClient(timeout=timeout(GENERATE_TIMEOUT_SECONDS)) as client:
        uploaded = await post_multipart(
            client,
            credentials,
            TEMPLATE_UPLOAD_PATH,
            STORAGE_TEMPLATE,
            template.name,
            template_bytes,
            "template upload",
        )
        template_urn = first_uploaded_id(uploaded, "template upload")
        staged = await post_multipart(
            client,
            credentials,
            DATA_UPLOAD_PATH,
            STORAGE_DATA,
            data_filename(request.document_name),
            json.dumps(data).encode("utf-8"),
            "data upload",
        )
        data_urn = first_uploaded_id(staged, "data upload")
        payload = await post_json(
            client,
            credentials,
            GENERATE_PATH,
            generate_body(template, template_urn, data_urn, request),
            "generate",
            GENERATE_TIMEOUT_SECONDS,
        )
        document = generated_document(payload, template_urn, data_urn)
        if not request.output_path:
            return document
        return await save_document(client, credentials, document, Path(request.output_path))
