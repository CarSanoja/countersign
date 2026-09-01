"""The seventh agent: it prepares the envelope, and it cannot sign it.

No model is called here. Nothing in this handoff needs judgement, so a model
would only add a way to be talked out of the boundary.

The agent asks the capability gate twice, against the same account and the same
host. Once for ``foxit_prepare_envelope``, which resolves to ``envelope.prepare``
and is granted. Once for ``foxit_execute_signature``, which resolves to
``signature.execute`` and is refused, because no agent in the fleet holds it.
That second attempt is deliberate: a power never exercised leaves no trace, and
the refusal is the product. It rides back in the payload so the trace and the UI
can show a person exactly where the pipeline stopped and why.

Defence in depth: were the gate ever misconfigured to grant signature.execute,
the dispatch path is still refused in the transport layer, and that second
refusal is raised rather than swallowed.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from autocurricula.tools.base import ToolResult

from countersign.agents.capability_gate import CapabilityDenial, denial, gate
from countersign.fleet.capabilities import CountersignCapability
from countersign.fleet.roster import ENVELOPE_PREPARER_ID, FLEET
from countersign.tools.foxit_esign import foxit_prepare_envelope
from countersign.tools.foxit_esign_client import attempt

PREPARE_TOOL = "foxit_prepare_envelope"
SIGNATURE_TOOL = "foxit_execute_signature"
DISPATCH_PATH = "/folders/sendDraftFolder"
TRANSPORT = "foxit transport"
CALLS_A_MODEL = False
AWAITING = (
    "a person who holds signature.execute; the envelope is a draft, no email left, "
    "and no signing session exists"
)

PrepareTool = Callable[..., Awaitable[ToolResult]]
DispatchCall = Callable[..., Awaitable[tuple[dict[str, Any] | None, str | None]]]


class SignatureBreach(RuntimeError):
    """The gate granted signature.execute and the transport did not stop it."""


def roster_grant() -> frozenset[str]:
    """The capabilities the roster grants this agent, and nothing beyond them."""
    for agent in FLEET:
        if agent.agent_id == ENVELOPE_PREPARER_ID:
            return frozenset(str(capability) for capability in agent.capabilities)
    raise RuntimeError(f"{ENVELOPE_PREPARER_ID} is absent from the fleet roster")


def _as_pdf_name(document_name: str) -> str:
    """Foxit reads the extension off the file name, and a vendor called
    Name.com turns "Bank verification - Name.com Inc" into file type "com".
    """
    cleaned = document_name.strip() or "document"
    return cleaned if cleaned.lower().endswith(".pdf") else f"{cleaned}.pdf"


class EnvelopePreparer:
    """Builds the signature envelope, tries to execute it, and is denied."""

    agent_id = ENVELOPE_PREPARER_ID
    calls_a_model = CALLS_A_MODEL

    def __init__(
        self,
        prepare_tool: PrepareTool = foxit_prepare_envelope,
        dispatch: DispatchCall = attempt,
    ) -> None:
        self.held = roster_grant()
        self._prepare_tool = prepare_tool
        self._dispatch = dispatch

    async def prepare(
        self,
        document_url: str,
        document_name: str,
        parties: list[dict[str, Any]],
        fields: list[dict[str, Any]] | None = None,
        folder_name: str = "",
        metadata: dict[str, str] | None = None,
    ) -> ToolResult:
        """Prepare an envelope for the generated document, then stop at the gate."""
        refused = self.gate(PREPARE_TOOL)
        if refused is not None:
            return ToolResult(
                ok=False,
                error=f"{PREPARE_TOOL} denied: {refused.reason}",
                payload={"denials": [refused.model_dump(mode="json")]},
            )
        prepared = await self._prepare_tool(
            folder_name=folder_name or document_name,
            file_urls=[document_url],
            file_names=[_as_pdf_name(document_name)],
            parties=parties,
            fields=fields or [],
            metadata={**(metadata or {}), "prepared_by": self.agent_id},
        )
        if not prepared.ok:
            return prepared
        try:
            denials = await self.attempt_signature(prepared.payload.get("folder_id"))
        except SignatureBreach as breach:
            return ToolResult(
                ok=False,
                error=str(breach),
                payload={**prepared.payload, "signature_executed": "unknown"},
            )
        return ToolResult.success(
            {
                **prepared.payload,
                "prepared_by": self.agent_id,
                "calls_a_model": CALLS_A_MODEL,
                "signature_attempted": True,
                "signature_executed": False,
                "denials": [record.model_dump(mode="json") for record in denials],
                "awaiting": AWAITING,
            }
        )

    async def attempt_signature(self, folder_id: Any) -> list[CapabilityDenial]:
        """Try to sign the envelope this agent just built. The gate says no."""
        refused = self.gate(SIGNATURE_TOOL)
        if refused is not None:
            return [refused]
        return [await self._refused_by_transport(folder_id)]

    def gate(self, tool: str) -> CapabilityDenial | None:
        """Ask the capability gate on this agent's own grant."""
        return gate(self.agent_id, tool, self.held)

    async def _refused_by_transport(self, folder_id: Any) -> CapabilityDenial:
        """Reached only if the gate is misconfigured. The transport refuses too."""
        _, error = await self._dispatch("POST", DISPATCH_PATH, {"folderId": folder_id})
        if error is None:
            raise SignatureBreach(
                f"the gate granted {SIGNATURE_TOOL} and {DISPATCH_PATH} answered for folder "
                f"{folder_id}: the envelope may have been dispatched. Check it by hand"
            )
        return denial(
            self.agent_id,
            SIGNATURE_TOOL,
            CountersignCapability.SIGNATURE_EXECUTE,
            TRANSPORT,
            error,
            True,
        )


async def prepare_envelope_for_signature(
    document_url: str,
    document_name: str,
    parties: list[dict[str, Any]],
    fields: list[dict[str, Any]] | None = None,
    folder_name: str = "",
    metadata: dict[str, str] | None = None,
) -> ToolResult:
    """Entry point for the handoff stage. Mutates external state: one draft envelope."""
    return await EnvelopePreparer().prepare(
        document_url=document_url,
        document_name=document_name,
        parties=parties,
        fields=fields,
        folder_name=folder_name,
        metadata=metadata,
    )


__all__ = [
    "AWAITING", "CALLS_A_MODEL", "DISPATCH_PATH", "PREPARE_TOOL", "SIGNATURE_TOOL",
    "TRANSPORT", "EnvelopePreparer", "SignatureBreach", "prepare_envelope_for_signature",
    "roster_grant",
]
