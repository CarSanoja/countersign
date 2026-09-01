"""The shape of a generation request and of the document that comes back.

The enums here are narrower than the prose in Doctavian's own guide: a template
is only ever docx or xlsx, and the extension is matched case-sensitively, so an
uppercase .DOCX is rejected as an invalid format. Checking that locally turns a
billed round trip into an immediate, readable failure.
"""

from pathlib import Path
from typing import Any

from autocurricula.schemas.common import StrictBaseModel
from pydantic import Field

from countersign.tools.doctavian_envelope import (
    DoctavianApiError,
    consumption,
    envelope_data,
    storage_id,
)

TEMPLATE_FORMATS: dict[str, str] = {".docx": "docx", ".xlsx": "xlsx"}
OUTPUT_FORMATS = frozenset({"pdf", "docx", "xlsx"})
LOAD_METHOD = "Storage"
DEFAULT_LOCALE = "en"
DEFAULT_TIMEZONE = "Europe/Dublin"


class GenerationRequest(StrictBaseModel):
    document_name: str
    file_format: str = "pdf"
    locale: str = DEFAULT_LOCALE
    timezone: str = DEFAULT_TIMEZONE
    external_id: str = ""
    output_path: str = ""


class GeneratedDocument(StrictBaseModel):
    name: str
    file_format: str
    delivery_method: str
    urn: str
    storage_id: str
    template_urn: str
    data_urn: str
    consumption: dict[str, float] = Field(default_factory=dict)
    operation_id: str = ""
    local_path: str = ""
    download_storage_type: str = ""


def template_problem(template: Path) -> str:
    if template.suffix not in TEMPLATE_FORMATS:
        accepted = ", ".join(sorted(TEMPLATE_FORMATS))
        return (
            f"template {template.name!r} is not a generatable Doctavian template: the API "
            f"matches the suffix case-sensitively and generation accepts only {accepted}"
        )
    if not template.is_file():
        return f"template file not found: {template}"
    return ""


def request_problem(request: GenerationRequest) -> str:
    if request.file_format not in OUTPUT_FORMATS:
        return (
            f"file_format must be one of {sorted(OUTPUT_FORMATS)}, "
            f"got {request.file_format!r}"
        )
    if not request.document_name.strip():
        return "document_name is required and must not carry a file extension"
    return ""


def data_filename(document_name: str) -> str:
    """Data upload validates the .json suffix and never parses the body."""
    kept = "".join(c if c.isalnum() or c in "-_" else "-" for c in document_name)
    return f"{kept.strip('-').lower() or 'countersign-data'}.json"


def generate_body(
    template: Path,
    template_urn: str,
    data_urn: str,
    request: GenerationRequest,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "template": {
            "name": template.name,
            "urn": template_urn,
            "fileFormat": TEMPLATE_FORMATS[template.suffix],
            "loadMethod": LOAD_METHOD,
        },
        "data": {"urn": data_urn, "loadMethod": LOAD_METHOD},
        "document": {
            "name": request.document_name.strip(),
            "fileFormat": request.file_format,
            "deliveryMethod": LOAD_METHOD,
            "path": "root",
            "locale": request.locale,
            "timezone": request.timezone,
        },
    }
    if request.external_id:
        body["externalContext"] = {"id": request.external_id}
    return body


def generated_document(
    payload: dict[str, Any], template_urn: str, data_urn: str
) -> GeneratedDocument:
    document = envelope_data(payload).get("document")
    urn = str(document.get("urn", "")) if isinstance(document, dict) else ""
    if not isinstance(document, dict) or not urn:
        raise DoctavianApiError(
            f"doctavian generate returned no document urn: {str(payload)[:400]}"
        )
    return GeneratedDocument(
        name=str(document.get("name", "")),
        file_format=str(document.get("fileFormat", "")),
        delivery_method=str(document.get("deliveryMethod", "")),
        urn=urn,
        storage_id=storage_id(urn),
        template_urn=template_urn,
        data_urn=data_urn,
        consumption=consumption(payload),
        operation_id=str(payload.get("operationId", "")),
    )
