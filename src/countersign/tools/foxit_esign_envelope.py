"""The shape of an envelope, and the checks Foxit will not do for you.

Foxit accepts an envelope whose fields point at a party that was never
declared: the call returns success and those fields are dropped in silence, so
a required signature is simply never routed. The same silence covers a
document list whose names and URLs do not line up. Both are checked here,
before anything leaves the process.

The flags that would turn preparation into execution live in ``HOLD_AT_DRAFT``
and are written into every body explicitly, even though false is their default,
because the default is the only thing standing between a draft and an email to
a counterparty.
"""

from typing import Any, Literal

from autocurricula.schemas.common import StrictBaseModel
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

HOLD_AT_DRAFT: dict[str, bool] = {
    "sendNow": False,
    "createEmbeddedSigningSession": False,
    "createEmbeddedSigningSessionForAllParties": False,
    "createEmbeddedSendingSession": False,
    "selfSign": False,
}

DRAFT_STATUS = "DRAFT"

FieldType = Literal[
    "text", "textbox", "signature", "initial", "date", "checkbox", "dropdown",
    "attachment", "image", "secure", "formulafield", "payfield", "accept", "decline",
]
Permission = Literal[
    "FILL_FIELDS_AND_SIGN", "FILL_FIELDS_ONLY", "SIGN_ONLY", "VIEW_ONLY", "PARTY_ASSIGNER"
]
SIGNING_FIELD_TYPES: frozenset[str] = frozenset({"signature", "initial"})


class FoxitModel(StrictBaseModel):
    model_config = ConfigDict(
        extra="forbid", alias_generator=to_camel, populate_by_name=True
    )


class EnvelopeParty(FoxitModel):
    first_name: str
    last_name: str
    email_id: str
    permission: Permission = "FILL_FIELDS_AND_SIGN"
    sequence: int = 1
    workflow_sequence: int = 1


class EnvelopeField(FoxitModel):
    type: FieldType
    party: int
    x: float
    y: float
    width: float
    height: float
    document_number: int = 1
    page_number: int = 1
    name: str | None = None
    required: bool = True
    date_format: str | None = None
    read_only: bool | None = None
    system_field: bool | None = None


class PrepareEnvelopeRequest(FoxitModel):
    folder_name: str
    file_urls: list[str]
    file_names: list[str]
    parties: list[EnvelopeParty]
    fields: list[EnvelopeField] = []
    input_type: Literal["url"] = "url"
    sign_in_sequence: bool = True
    process_text_tags: bool = False
    process_acro_fields: bool = False
    metadata: dict[str, str] | None = None


def coherence_problems(request: PrepareEnvelopeRequest) -> list[str]:
    """Everything Foxit would accept and then quietly discard."""
    problems: list[str] = []
    if len(request.file_urls) != len(request.file_names):
        problems.append(
            f"{len(request.file_urls)} file_urls against {len(request.file_names)} file_names"
        )
    if not request.file_urls:
        problems.append("no document to sign")
    if not request.parties:
        problems.append("no parties, so nobody could ever be asked to sign")

    sequences = [party.sequence for party in request.parties]
    duplicated = sorted({seq for seq in sequences if sequences.count(seq) > 1})
    if duplicated:
        problems.append(f"party sequences repeat: {duplicated}")

    unknown = sorted({field.party for field in request.fields if field.party not in sequences})
    if unknown:
        problems.append(
            f"fields point at undeclared parties {unknown}; foxit would drop them silently"
        )

    signable = {field.party for field in request.fields if field.type in SIGNING_FIELD_TYPES}
    if not signable and not request.process_text_tags:
        problems.append("no signature or initial field, so the envelope cannot be signed")
    return problems


def create_folder_body(request: PrepareEnvelopeRequest) -> dict[str, Any]:
    """Request body for /folders/createfolder, pinned to draft."""
    body = request.model_dump(by_alias=True, exclude_none=True)
    body.update(HOLD_AT_DRAFT)
    return body


def party_digest(request: PrepareEnvelopeRequest) -> list[dict[str, Any]]:
    """Who this envelope would ask, for the human deciding whether to send it."""
    return [
        {
            "sequence": party.sequence,
            "name": f"{party.first_name} {party.last_name}".strip(),
            "email_id": party.email_id,
            "permission": party.permission,
            "field_count": sum(1 for field in request.fields if field.party == party.sequence),
        }
        for party in request.parties
    ]
