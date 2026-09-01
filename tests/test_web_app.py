"""Offline tests for the FastAPI web shell (sae_demo/web_app.py).

No network calls, no provider calls, no Emotional Memory access.
M5A tests exercise the health/status API and static frontend serving.
M5B tests exercise the scenario-listing and in-memory scenario-run API
(sae_demo.web_app's own adapter around the existing, unchanged
ScenarioEngine). Every test in this module asserts that provider and
memory functionality are never touched and that no private material
leaks into any HTTP response.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sae_demo import memory_loader, nebius_provider
from sae_demo.config import DEFAULT_NEBIUS_MODEL
from sae_demo.web_app import BUILTIN_SCENARIOS, app

# Private-material fragments that must never appear in any response
# from this app, in any test in this module.
FORBIDDEN_FRAGMENTS = (
    "XNET",
    "XINJ",
    "C:\\Projects\\SAE",
    "/mnt/SAE",
    ".local/memory",
    "NEBIUS_API_KEY_VALUE_SHOULD_NEVER_APPEAR",
)


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _assert_no_forbidden_material(text: str) -> None:
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in text


# -- /api/health --------------------------------------------------------


def test_health_returns_200_and_expected_safe_response(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    _assert_no_forbidden_material(response.text)


# -- /api/status ---------------------------------------------------------


def test_status_returns_200(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    response = client.get("/api/status")

    assert response.status_code == 200


def test_status_never_includes_api_key_value(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_key = "NEBIUS_API_KEY_VALUE_SHOULD_NEVER_APPEAR"
    monkeypatch.setenv("NEBIUS_API_KEY", fake_key)

    response = client.get("/api/status")

    assert response.status_code == 200
    assert fake_key not in response.text
    _assert_no_forbidden_material(response.text)


def test_status_works_when_api_key_absent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    response = client.get("/api/status")
    body = response.json()

    assert response.status_code == 200
    assert body["provider_configured"] is False


def test_status_reports_provider_configured_as_boolean_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "some-fake-value")

    response = client.get("/api/status")
    body = response.json()

    assert isinstance(body["provider_configured"], bool)
    assert body["provider_configured"] is True


def test_status_public_fields_and_no_private_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    response = client.get("/api/status")
    body = response.json()

    assert body["application"] == "SAE-DEMO"
    assert body["stage"] == "M5B"
    assert body["backend_status"] == "ok"
    assert body["target_model"] == DEFAULT_NEBIUS_MODEL
    assert body["memory_feature_status"] == "not active in M5B"
    assert "M5B" in body["scenario_feature_status"]
    _assert_no_forbidden_material(response.text)


# -- frontend serving ------------------------------------------------------


def test_root_page_returns_frontend_html(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SAE-DEMO" in response.text
    _assert_no_forbidden_material(response.text)


def test_root_page_renders_scenario_run_ui(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="scenario-select"' in response.text
    assert 'id="start-scenario-btn"' in response.text
    assert 'id="next-segment-btn"' in response.text
    assert "Model response will appear in M5C" in response.text
    _assert_no_forbidden_material(response.text)


def test_static_css_and_js_assets_resolve(client: TestClient) -> None:
    css_response = client.get("/static/styles.css")
    js_response = client.get("/static/app.js")

    assert css_response.status_code == 200
    assert js_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
    assert "javascript" in js_response.headers["content-type"]
    _assert_no_forbidden_material(css_response.text)
    _assert_no_forbidden_material(js_response.text)


# -- boundary: no provider call, no memory access ---------------------------


def test_no_provider_call_while_serving_health_status_root(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_constructed(*args, **kwargs):
        raise AssertionError("NebiusProvider must not be constructed by web_app")

    monkeypatch.setattr(
        nebius_provider.NebiusProvider, "__init__", _fail_if_constructed
    )

    for path in ("/api/health", "/api/status", "/", "/static/styles.css", "/static/app.js"):
        response = client.get(path)
        assert response.status_code == 200

    # Also run a full scenario to completion under the same guard: M5B
    # must not construct a provider at any point in the run flow either.
    _run_full_scenario(client, "greenhouse")


def test_no_emotional_memory_artifact_is_accessed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("load_opaque_memory_artifact must not be called by web_app")

    monkeypatch.setattr(
        memory_loader, "load_opaque_memory_artifact", _fail_if_called
    )

    for path in ("/api/health", "/api/status", "/"):
        response = client.get(path)
        assert response.status_code == 200

    _run_full_scenario(client, "new_studio")


def test_private_sae_paths_and_ids_absent_from_all_responses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "some-fake-value")

    for path in ("/api/health", "/api/status", "/", "/static/styles.css", "/static/app.js"):
        response = client.get(path)
        _assert_no_forbidden_material(response.text)

    responses = _run_full_scenario(client, "greenhouse")
    for response in responses:
        _assert_no_forbidden_material(response.text)


# -- M5B: GET /api/scenarios ------------------------------------------------


def test_list_scenarios_returns_exactly_the_public_safe_fixtures(
    client: TestClient,
) -> None:
    response = client.get("/api/scenarios")
    body = response.json()

    assert response.status_code == 200
    ids = {entry["id"] for entry in body}
    assert ids == set(BUILTIN_SCENARIOS)
    assert ids == {"greenhouse", "new_studio"}
    for entry in body:
        assert set(entry) == {"id", "title", "description", "segment_count"}
        assert entry["segment_count"] == 7


def test_scenario_listing_excludes_raw_segment_text(client: TestClient) -> None:
    response = client.get("/api/scenarios")

    assert response.status_code == 200
    # Fragments that only appear inside individual segment bodies (not
    # in the scenario-level title/description) should not leak into the
    # listing -- only id/title/description/segment_count are returned
    # for each entry.
    assert "crooked pane of glass" not in response.text
    assert "clamps into one box" not in response.text
    for entry in response.json():
        assert "text" not in entry
        assert "segments" not in entry


# -- M5B: run lifecycle ------------------------------------------------


def test_start_run_creates_in_memory_frozen_run(client: TestClient) -> None:
    response = client.post("/api/runs", json={"scenario_id": "greenhouse"})
    body = response.json()

    assert response.status_code == 201
    assert body["mode"] == "frozen"
    assert body["run_id"]

    # The run is retrievable afterward -- it exists in the registry.
    follow_up = client.get(f"/api/runs/{body['run_id']}")
    assert follow_up.status_code == 200
    assert follow_up.json()["run_id"] == body["run_id"]


def test_start_run_returns_first_segment_correctly(client: TestClient) -> None:
    response = client.post("/api/runs", json={"scenario_id": "greenhouse"})
    body = response.json()

    assert body["scenario_id"] == "greenhouse"
    assert body["total_segments"] == 7
    assert body["current_segment_number"] == 1
    assert body["completed"] is False
    assert body["transcript"] == []
    assert body["current_segment"]["segment_id"] == "greenhouse_01_background"
    assert body["current_segment"]["role"] == "background_attachment"
    assert body["current_segment"]["role_label"] == "Background & attachment"
    assert body["current_segment"]["text"]


def test_advance_moves_exactly_one_segment(client: TestClient) -> None:
    start = client.post("/api/runs", json={"scenario_id": "greenhouse"}).json()
    run_id = start["run_id"]

    response = client.post(f"/api/runs/{run_id}/advance")
    body = response.json()

    assert response.status_code == 200
    assert len(body["transcript"]) == 1
    assert body["transcript"][0]["segment_id"] == "greenhouse_01_background"
    assert body["current_segment_number"] == 2
    assert body["current_segment"]["segment_id"] == "greenhouse_02_possibility"
    assert body["completed"] is False


def test_segment_order_is_preserved_through_a_run(client: TestClient) -> None:
    expected_order = [
        "studio_01_background",
        "studio_02_possibility",
        "studio_03_irreversibility",
        "studio_04_neutral",
        "studio_05_meaning",
        "studio_06_pressure",
        "studio_07_closure",
    ]
    start = client.post("/api/runs", json={"scenario_id": "new_studio"}).json()
    run_id = start["run_id"]

    for _ in expected_order:
        client.post(f"/api/runs/{run_id}/advance")

    final = client.get(f"/api/runs/{run_id}").json()
    sent_ids = [segment["segment_id"] for segment in final["transcript"]]
    assert sent_ids == expected_order


def test_full_run_reaches_completed_state(client: TestClient) -> None:
    start = client.post("/api/runs", json={"scenario_id": "greenhouse"}).json()
    run_id = start["run_id"]

    body = None
    for _ in range(7):
        body = client.post(f"/api/runs/{run_id}/advance").json()

    assert body["completed"] is True
    assert body["current_segment"] is None
    assert len(body["transcript"]) == 7
    assert body["current_segment_number"] == body["total_segments"] == 7


def test_advance_after_completion_returns_safe_error(client: TestClient) -> None:
    start = client.post("/api/runs", json={"scenario_id": "greenhouse"}).json()
    run_id = start["run_id"]
    for _ in range(7):
        client.post(f"/api/runs/{run_id}/advance")

    response = client.post(f"/api/runs/{run_id}/advance")

    assert response.status_code == 409
    assert "detail" in response.json()
    assert "Traceback" not in response.text
    _assert_no_forbidden_material(response.text)


def test_unknown_scenario_returns_safe_4xx(client: TestClient) -> None:
    response = client.post("/api/runs", json={"scenario_id": "not_a_real_scenario"})

    assert 400 <= response.status_code < 500
    assert "detail" in response.json()
    assert "Traceback" not in response.text
    _assert_no_forbidden_material(response.text)


def test_unknown_run_returns_safe_404(client: TestClient) -> None:
    get_response = client.get("/api/runs/does-not-exist")
    advance_response = client.post("/api/runs/does-not-exist/advance")

    assert get_response.status_code == 404
    assert advance_response.status_code == 404
    for response in (get_response, advance_response):
        assert "detail" in response.json()
        assert "Traceback" not in response.text
        _assert_no_forbidden_material(response.text)


def test_malformed_start_request_returns_safe_error(client: TestClient) -> None:
    response = client.post("/api/runs", json={"not_scenario_id": "greenhouse"})

    assert response.status_code == 422
    assert "Traceback" not in response.text
    _assert_no_forbidden_material(response.text)


def _run_full_scenario(client: TestClient, scenario_id: str) -> list:
    """Start and fully advance one scenario; return every HTTP response."""

    responses = []
    start_response = client.post("/api/runs", json={"scenario_id": scenario_id})
    responses.append(start_response)
    run_id = start_response.json()["run_id"]

    total_segments = start_response.json()["total_segments"]
    for _ in range(total_segments):
        responses.append(client.post(f"/api/runs/{run_id}/advance"))

    return responses
