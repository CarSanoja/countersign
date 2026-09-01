"""Foxit eSign tools for COUNTERSIGN. Capability: ``envelope.prepare``.

Every tool here stops at DRAFT. The envelope ends up complete — document,
recipients, fields — and inert: no invitation email leaves, and no embedded
signing session is minted, so nobody can sign until a person decides to send
it. In this API the frontier is the flags rather than the endpoint, so the
draft status is asserted on the response instead of assumed from the request.

Signing lives behind ``signature.execute``, which no agent in the fleet holds.
The paths that dispatch, remind, cancel or delete are refused in the transport
layer, not merely left uncalled.
"""

from typing import Any

from autocurricula.tools.base import ToolResult, as_function_tool
from pydantic import ValidationError

from countersign.tools.foxit_esign_client import CAPABILITY, attempt
from countersign.tools.foxit_esign_envelope import (
    DRAFT_STATUS,
    PrepareEnvelopeRequest,
    coherence_problems,
    create_folder_body,
    party_digest,
)

CREATE_FOLDER_PATH = "/folders/createfolder"
FOLDER_DETAIL_PATH = "/folders/myfolder"
FOLDER_IDS_PATH = "/folders/getAllFolderIdsByStatus"
VALIDATION_ERROR_LIMIT = 600


async def foxit_prepare_envelope(
    folder_name: str,
    file_urls: list[str],
    file_names: list[str],
    parties: list[dict[str, Any]],
    fields: list[dict[str, Any]] | None = None,
    metadata: dict[str, str] | None = None,
    sign_in_sequence: bool = True,
    process_text_tags: bool = False,
) -> ToolResult:
    """Build a signature envelope and leave it in DRAFT, awaiting a person.

    Mutates external state: an envelope is created in the Foxit account. It
    dispatches nothing — no email is sent and no signing session exists, so no
    counterparty can act on it until a human executes it out of band.
    """
    try:
        request = PrepareEnvelopeRequest(
            folder_name=folder_name,
            file_urls=file_urls,
            file_names=file_names,
            parties=parties,
            fields=fields or [],
            metadata=metadata,
            sign_in_sequence=sign_in_sequence,
            process_text_tags=process_text_tags,
        )
    except ValidationError as error:
        return ToolResult.failure(f"invalid envelope: {str(error)[:VALIDATION_ERROR_LIMIT]}")

    problems = coherence_problems(request)
    if problems:
        return ToolResult.failure(f"envelope would be silently mangled: {'; '.join(problems)}")

    payload, error = await attempt("POST", CREATE_FOLDER_PATH, create_folder_body(request))
    if error is not None or payload is None:
        return ToolResult.failure(error or "foxit esign returned no body")

    folder = payload.get("folder") or {}
    folder_id = folder.get("folderId")
    status = folder.get("folderStatus")
    if payload.get("embeddedSigningSessions"):
        return ToolResult.failure(
            f"envelope {folder_id} came back with a signing session; it is live. "
            "Cancel it by hand: this tool may not mint signing capability"
        )
    if status != DRAFT_STATUS:
        return ToolResult.failure(
            f"envelope {folder_id} is {status}, not {DRAFT_STATUS}; it may already be "
            "signable. Review it by hand before anything else happens"
        )
    return ToolResult.success(
        {
            "capability": CAPABILITY,
            "folder_id": folder_id,
            "folder_status": status,
            "folder_name": folder.get("folderName"),
            "document_ids": folder.get("folderDocumentIds") or [],
            "parties": party_digest(request),
            "dispatched": False,
            "awaiting": "a person to send it; no email was sent and no signing session exists",
        }
    )


async def foxit_envelope_status(folder_id: int) -> ToolResult:
    """Read one envelope's status and progress.

    Does not mutate external state. Party access URLs are deliberately not
    surfaced: a readable signing link would be signing capability by another
    name.
    """
    payload, error = await attempt("GET", FOLDER_DETAIL_PATH, params={"folderId": folder_id})
    if error is not None or payload is None:
        return ToolResult.failure(error or "foxit esign returned no body")
    folder = payload.get("folder") or {}
    recipients = folder.get("folderRecipientParties") or []
    return ToolResult.success(
        {
            "capability": CAPABILITY,
            "folder_id": folder.get("folderId"),
            "folder_status": folder.get("folderStatus"),
            "folder_name": folder.get("folderName"),
            "created_at": folder.get("folderCreationDate"),
            "sent_at": folder.get("folderSentDate"),
            "dispatched": folder.get("folderStatus") != DRAFT_STATUS,
            "recipient_count": len(recipients),
            "document_ids": folder.get("folderDocumentIds") or [],
        }
    )


async def foxit_list_prepared_envelopes(date_from: str, date_to: str) -> ToolResult:
    """List envelope ids still in DRAFT, so pending handoffs can be reconciled.

    Does not mutate external state. Dates are YYYY-MM-DD and Foxit rejects a
    window wider than six months.
    """
    params = {"status": DRAFT_STATUS, "dateFrom": date_from, "dateTo": date_to}
    payload, error = await attempt("GET", FOLDER_IDS_PATH, params=params)
    if error is not None or payload is None:
        return ToolResult.failure(error or "foxit esign returned no body")
    folder_ids = payload.get("allFolderIds") or []
    return ToolResult.success(
        {
            "capability": CAPABILITY,
            "folder_ids": folder_ids,
            "count": len(folder_ids),
            "window": {"from": date_from, "to": date_to},
        }
    )


def prepare_envelope_via_unified_gateway(*_: Any, **__: Any) -> ToolResult:
    """Unimplemented: which credential pair reaches the unified gateway is unknown.

    The Postman collection says eSign needs its own client_id/client_secret and
    OAuth2 bearer against na1.foxitesign.foxit.com/api; the August 2026 blog says
    the PDF Services pair authenticates eSign through client_id/client_secret
    headers on na1.fusion.foxit.com/esign/api/v1. Both hosts answer, no route
    under /esign/api/v1 has been confirmed, and the gateway rejects on missing
    credentials before routing, so an unknown path is indistinguishable from a
    known one. Resolving it needs real provisioned credentials.
    """
    raise NotImplementedError(
        "unresolved: whether FOXIT_ESIGN_CLIENT_ID/SECRET also authenticate "
        "https://na1.fusion.foxit.com/esign/api/v1 via client_id/client_secret headers. "
        "Needs live credentials from the provisioned eSign account to settle."
    )


def prepare_embedded_sending_session(*_: Any, **__: Any) -> ToolResult:
    """Unimplemented: an embedded sending session may not stay in DRAFT.

    createEmbeddedSendingSession=true with sendNow=false is the flow this
    product wants — a person drags fields and presses Send — but whether the
    envelope stays DRAFT or goes SHARED, as it does for a signing session, is
    undocumented and unverified. Guessing here would mean shipping an envelope
    that might already be live.
    """
    raise NotImplementedError(
        "unverified: folderStatus after createEmbeddedSendingSession=true with "
        "sendNow=false. Needs one live call against a provisioned account, reading "
        "folderStatus back from /folders/myfolder, before it can be exposed."
    )


PREPARE_ENVELOPE_TOOL = as_function_tool(foxit_prepare_envelope)
ENVELOPE_STATUS_TOOL = as_function_tool(foxit_envelope_status)
LIST_PREPARED_ENVELOPES_TOOL = as_function_tool(foxit_list_prepared_envelopes)
