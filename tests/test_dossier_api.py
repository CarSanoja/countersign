"""The two ways into the same renderer: a posted run, and the bundled example.

Nothing here touches a provider. The demo route reads a file and the dossier
route reads its own request body, so the surface can be exercised with every
credential absent.
"""

import json

import pytest
from fastapi.testclient import TestClient

from countersign.api.dossier_sample import SampleUnavailable, load_sample, sample_path
from countersign.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_the_bare_url_lands_on_the_demo(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/demo"


def test_health_is_answerable_without_any_credential(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_the_demo_route_serves_html_that_is_not_cached(client: TestClient) -> None:
    response = client.get("/demo")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert "foxit_execute_signature" in response.text


def test_the_example_posts_back_to_the_live_route_unchanged(client: TestClient) -> None:
    payload = client.get("/demo.json")
    assert payload.status_code == 200
    posted = client.post("/dossier", json=payload.json())
    assert posted.status_code == 200
    assert posted.text == client.get("/demo").text


def test_a_body_that_is_not_an_assessment_is_refused(client: TestClient) -> None:
    assert client.post("/dossier", json={"verdict": {"run_id": "x"}}).status_code == 422


def test_a_high_verdict_with_no_signal_is_refused_at_the_door(client: TestClient) -> None:
    payload = json.loads(sample_path().read_text(encoding="utf-8"))
    payload["verdict"]["signals"] = []
    assert client.post("/dossier", json=payload).status_code == 422


def test_a_missing_example_is_named_rather_than_half_served(tmp_path) -> None:
    with pytest.raises(SampleUnavailable):
        load_sample(tmp_path / "absent.json")


def test_a_stale_example_is_named_rather_than_half_served(tmp_path) -> None:
    broken = tmp_path / "dossier.json"
    broken.write_text('{"verdict": {"run_id": "x"}}', encoding="utf-8")
    with pytest.raises(SampleUnavailable):
        load_sample(broken)
