"""The handoff stops at the gate, and the denial is evidence. Asserted, not documented.

No envelope is created against the live account: the eSign quota is 25 in total,
so every request here is answered by httpx.MockTransport.
"""

from typing import Any

import httpx
import pytest

from countersign.agents.envelope_preparer import (
    DISPATCH_PATH,
    PREPARE_TOOL,
    SIGNATURE_TOOL,
    EnvelopePreparer,
    SignatureBreach,
)
from countersign.tools.foxit_esign_client import base_url

DOCUMENT_URL = "https://example.invalid/bank-verification.pdf"
DOCUMENT_NAME = "bank-verification"
PARTIES: list[dict[str, Any]] = [
    {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email_id": "ada@vendor.invalid",
        "sequence": 1,
    }
]
FIELDS: list[dict[str, Any]] = [
    {"type": "signature", "party": 1, "x": 100, "y": 200, "width": 160, "height": 40}
]


def _folder_response() -> dict[str, Any]:
    return {
        "result": "success",
        "folder": {
            "folderId": 987654,
            "folderName": DOCUMENT_NAME,
            "folderStatus": "DRAFT",
            "folderDocumentIds": [111],
        },
    }


@pytest.fixture
def recorded_paths(monkeypatch) -> list[str]:
    """A Foxit that answers token and createfolder, and records every path asked for."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/oauth2/access_token"):
            return httpx.Response(
                200,
                json={"access_token": "test-token", "token_type": "bearer", "expires_in": 31535999},
            )
        if request.url.path.endswith("/folders/createfolder"):
            return httpx.Response(200, json=_folder_response())
        raise AssertionError(f"unexpected call to {request.url.path}")

    real_client = httpx.AsyncClient

    def client_on_mock(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_on_mock)
    monkeypatch.setenv("FOXIT_ESIGN_CLIENT_ID", "test-id")
    monkeypatch.setenv("FOXIT_ESIGN_CLIENT_SECRET", "test-secret")
    monkeypatch.delenv("FOXIT_ESIGN_ACCESS_TOKEN", raising=False)
    return paths


async def test_the_envelope_is_prepared_and_the_signature_is_denied(recorded_paths):
    result = await EnvelopePreparer().prepare(
        document_url=DOCUMENT_URL,
        document_name=DOCUMENT_NAME,
        parties=PARTIES,
        fields=FIELDS,
    )
    assert result.ok, result.error
    payload = result.payload
    assert payload["folder_status"] == "DRAFT"
    assert payload["dispatched"] is False
    assert payload["calls_a_model"] is False
    assert payload["signature_attempted"] is True
    assert payload["signature_executed"] is False

    denials = payload["denials"]
    assert len(denials) == 1
    denial = denials[0]
    assert denial["tool"] == SIGNATURE_TOOL
    assert denial["capability"] == "signature.execute"
    assert denial["human_only"] is True
    assert denial["agent_id"] == "envelope-preparer"
    assert denial["attempted_at"]


async def test_nothing_that_dispatches_an_envelope_is_ever_requested(recorded_paths):
    await EnvelopePreparer().prepare(
        document_url=DOCUMENT_URL,
        document_name=DOCUMENT_NAME,
        parties=PARTIES,
        fields=FIELDS,
    )
    assert recorded_paths
    for path in recorded_paths:
        assert not path.endswith(DISPATCH_PATH), f"{path} would send the envelope"


def test_the_agent_is_granted_preparation_and_refused_execution():
    preparer = EnvelopePreparer()
    assert preparer.gate(PREPARE_TOOL) is None
    denial = preparer.gate(SIGNATURE_TOOL)
    assert denial is not None
    assert denial.capability == "signature.execute"
    assert denial.human_only is True


def test_an_unmapped_tool_fails_closed():
    denial = EnvelopePreparer().gate("foxit_do_whatever_it_takes")
    assert denial is not None
    assert denial.capability is None


async def test_a_misconfigured_gate_raises_before_anything_is_sent(monkeypatch):
    """The breach is the grant, not the dispatch.

    An earlier version proved the transport would refuse by POSTing to the
    dispatch path and raising only if the call succeeded, which meant a
    permissive Foxit would have sent the envelope before the exception arrived.
    Holding the power is already the failure, so it raises without a request.
    """
    sent: list[str] = []

    async def record(method: str, path: str, *_: Any, **__: Any):
        sent.append(path)
        return None, "should never be reached"

    monkeypatch.setattr(
        "countersign.agents.capability_gate.agent_holds", lambda capability: True
    )
    preparer = EnvelopePreparer()
    preparer.held = frozenset({"envelope.prepare", "signature.execute"})
    monkeypatch.setattr(preparer, "_dispatch", record)

    with pytest.raises(SignatureBreach):
        await preparer.attempt_signature(987654)
    assert sent == [], "a request was made while refusing to make one"


async def test_a_transport_that_answers_instead_of_refusing_is_a_breach(monkeypatch):
    async def answers(*_: Any, **__: Any) -> tuple[dict[str, Any] | None, str | None]:
        return {"result": "success"}, None

    monkeypatch.setattr(
        "countersign.agents.capability_gate.agent_holds", lambda capability: True
    )
    preparer = EnvelopePreparer(dispatch=answers)
    preparer.held = frozenset({"envelope.prepare", "signature.execute"})
    with pytest.raises(SignatureBreach):
        await preparer.attempt_signature(987654)


def test_the_default_host_is_the_verified_one(monkeypatch):
    monkeypatch.delenv("FOXIT_ESIGN_BASE_URL", raising=False)
    assert base_url() == "https://na1.foxitesign.foxit.com/api"
