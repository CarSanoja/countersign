"""The dossier surface is closed by default, and says which way it is closed.

Three states matter and they must stay distinguishable: the token was never
configured (503, the deployment is incomplete), the token is configured and the
caller does not have it (401, the deployment is fine), and the caller has it
(200). Health stays reachable in all three, because a probe that needs the secret
cannot tell the platform whether the container came up.
"""

import json

import pytest
from fastapi.testclient import TestClient

from countersign.api.auth import API_TOKEN_ENV, token_matches
from countersign.api.dossier_sample import sample_path
from countersign.api.main import app

TOKEN = "a-token-only-the-deployment-knows"
GOOD = {"Authorization": f"Bearer {TOKEN}"}
DOSSIER_ROUTES = ("/demo", "/demo.json")


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv(API_TOKEN_ENV, raising=False)
    return TestClient(app)


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv(API_TOKEN_ENV, TOKEN)
    return TestClient(app)


def sample_payload() -> dict:
    return json.loads(sample_path().read_text(encoding="utf-8"))


@pytest.mark.parametrize("route", DOSSIER_ROUTES)
def test_an_unconfigured_token_closes_the_dossier_rather_than_opening_it(
    unconfigured: TestClient, route: str
) -> None:
    response = unconfigured.get(route)
    assert response.status_code == 503
    assert API_TOKEN_ENV in response.json()["detail"]


def test_the_posted_route_is_closed_too_when_the_token_is_unconfigured(
    unconfigured: TestClient,
) -> None:
    response = unconfigured.post("/dossier", json=sample_payload())
    assert response.status_code == 503


def test_a_correct_token_does_not_open_an_unconfigured_deployment(
    unconfigured: TestClient,
) -> None:
    """There is nothing to be correct against, so the guess must not become access."""
    assert unconfigured.get("/demo", headers=GOOD).status_code == 503


def test_a_token_of_only_whitespace_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_TOKEN_ENV, "   \n ")
    assert TestClient(app).get("/demo").status_code == 503


@pytest.mark.parametrize("route", DOSSIER_ROUTES)
def test_a_configured_deployment_refuses_a_caller_with_no_header(
    configured: TestClient, route: str
) -> None:
    response = configured.get(route)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": f"Bearer {TOKEN}x"},
        {"Authorization": f"Bearer {TOKEN[:-1]}"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": TOKEN},
        {"Authorization": "Bearer "},
    ],
)
def test_a_configured_deployment_refuses_every_shape_of_wrong_credential(
    configured: TestClient, header: dict[str, str]
) -> None:
    assert configured.get("/demo", headers=header).status_code == 401


def test_the_body_is_not_parsed_for_a_caller_who_has_not_authenticated(
    configured: TestClient,
) -> None:
    """A 422 would tell an anonymous caller the schema. The guard runs first."""
    assert configured.post("/dossier", json={"nonsense": True}).status_code == 401


@pytest.mark.parametrize("route", DOSSIER_ROUTES)
def test_the_right_token_reaches_the_dossier(configured: TestClient, route: str) -> None:
    response = configured.get(route, headers=GOOD)
    assert response.status_code == 200


def test_the_right_token_reaches_the_posted_route(configured: TestClient) -> None:
    response = configured.post("/dossier", json=sample_payload(), headers=GOOD)
    assert response.status_code == 200
    assert "foxit_execute_signature" in response.text


def test_a_secret_that_arrived_with_a_trailing_newline_still_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secret Manager hands back the newline; the deployment should not fail on it."""
    monkeypatch.setenv(API_TOKEN_ENV, f"{TOKEN}\n")
    assert TestClient(app).get("/demo", headers=GOOD).status_code == 200


def test_health_answers_whether_or_not_the_token_is_configured(
    unconfigured: TestClient,
) -> None:
    assert unconfigured.get("/healthz").json() == {"status": "ok"}


def test_health_answers_without_a_credential_on_a_configured_deployment(
    configured: TestClient,
) -> None:
    assert configured.get("/healthz").json() == {"status": "ok"}


def test_the_bare_url_still_redirects_without_a_credential(configured: TestClient) -> None:
    response = configured.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/demo"


@pytest.mark.parametrize(
    ("presented", "expected", "matches"),
    [
        ("same", "same", True),
        ("same", "SAME", False),
        ("", "same", False),
        ("ñ-token", "ñ-token", True),
        ("ñ-token", "n-token", False),
    ],
)
def test_the_comparison_is_exact_and_survives_bytes_outside_ascii(
    presented: str, expected: str, matches: bool
) -> None:
    assert token_matches(presented, expected) is matches
