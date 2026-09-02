"""Offline tests for the FastAPI web shell (sae_demo/web_app.py).

No network calls, no real provider calls, no real Emotional Memory
artifact is ever read. M5A tests exercise the health/status API and
static frontend serving. M5B tests exercise scenario listing and the
in-memory scenario-run lifecycle. M5C tests exercise Memory OFF/ON
run configuration, the real (but always mocked-in-tests) provider
call made on each "advance", the controlled-run invariants that must
hold between Memory OFF and Memory ON, and the safe-error behavior
required when configuration or a provider call fails. M5D tests
exercise the controlled comparison: creating a fresh opposite-memory-
mode "alternate" run of the same scenario from an already-completed
run, the pair-validation rules that keep a comparison from ever being
presented as complete unless it truly pairs one completed OFF run and
one completed ON run of the same scenario, and that the comparison
response never performs or implies any automated scoring/ranking.

Every provider call in this module goes through an in-process fake
(`mock_provider` / `reasoning_mock_provider` / `failing_mock_provider`
below) that never touches the network; every Memory ON test uses a
small, synthetic, test-only artifact written to `tmp_path`
(`configured_memory_artifact` / `tampered_memory_artifact` below) --
never a real prepared Emotional Memory artifact. Every test in this
module also asserts that no private material (a real API key value,
a private path, a memory payload, the behavioral-use policy text,
etc.) leaks into any HTTP response.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient

from sae_demo import custom_scenario, memory_loader, web_app
from sae_demo.compatibility_runner import (
    DEFAULT_BEHAVIORAL_USE_POLICY,
    DEFAULT_SYSTEM_MESSAGE,
)
from sae_demo.config import DEFAULT_NEBIUS_MODEL
from sae_demo.nebius_provider import NebiusCompletionResult, NebiusProviderError
from sae_demo.scenario import ROLE_ORDER
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

FAKE_API_KEY = "NEBIUS_API_KEY_VALUE_SHOULD_NEVER_APPEAR"

# A synthetic, test-only stand-in for a prepared Emotional Memory
# payload. Not derived from, and does not resemble, any real artifact
# or private SAE vocabulary -- it exists only so tests can assert the
# opaque pass-through behavior (present in ON, absent in OFF, never
# exposed in an HTTP response).
MEMORY_PAYLOAD_TEXT = (
    "Synthetic test-only background context payload, used for M5C "
    "tests only -- not a real Emotional Memory artifact."
)

FAKE_ASSISTANT_REPLY = "This is a fake assistant reply (test double, not a real model output)."


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _assert_no_forbidden_material(text: str) -> None:
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in text


# -- fake provider plumbing -------------------------------------------------
#
# None of these ever open a socket. Each records every message list it
# was asked to "complete" (as `.calls`), so tests can assert on exactly
# what was sent, without ever depending on real provider output.


class _FakeProviderRecorder:
    def __init__(self) -> None:
        self.calls: List[List[Dict[str, str]]] = []


def _make_fake_provider_class(recorder: _FakeProviderRecorder, *, reasoning_present: bool = False):
    class FakeNebiusProvider:
        def __init__(self, config, *, client=None) -> None:
            self.config = config

        def complete(self, messages, *, max_tokens: int = 100) -> NebiusCompletionResult:
            recorder.calls.append([dict(message) for message in messages])
            return NebiusCompletionResult(
                content=FAKE_ASSISTANT_REPLY,
                reasoning=("(fake reasoning trace)" if reasoning_present else None),
                finish_reason="stop",
                completion_tokens=8,
                reasoning_warning=reasoning_present,
            )

    return FakeNebiusProvider


def _make_failing_provider_class(recorder: _FakeProviderRecorder):
    class FailingNebiusProvider:
        def __init__(self, config, *, client=None) -> None:
            self.config = config

        def complete(self, messages, *, max_tokens: int = 100) -> NebiusCompletionResult:
            recorder.calls.append([dict(message) for message in messages])
            raise NebiusProviderError("Nebius request failed: FakeProviderFailure")

    return FailingNebiusProvider


@pytest.fixture()
def mock_provider(monkeypatch: pytest.MonkeyPatch) -> _FakeProviderRecorder:
    """A configured, fake, always-successful provider. No network call."""

    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)
    recorder = _FakeProviderRecorder()
    monkeypatch.setattr(web_app, "NebiusProvider", _make_fake_provider_class(recorder))
    return recorder


@pytest.fixture()
def reasoning_mock_provider(monkeypatch: pytest.MonkeyPatch) -> _FakeProviderRecorder:
    """Like `mock_provider`, but every reply carries a reasoning field."""

    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)
    recorder = _FakeProviderRecorder()
    monkeypatch.setattr(
        web_app, "NebiusProvider", _make_fake_provider_class(recorder, reasoning_present=True)
    )
    return recorder


@pytest.fixture()
def failing_mock_provider(monkeypatch: pytest.MonkeyPatch) -> _FakeProviderRecorder:
    """A configured, fake provider whose every call fails. No network call."""

    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)
    recorder = _FakeProviderRecorder()
    monkeypatch.setattr(web_app, "NebiusProvider", _make_failing_provider_class(recorder))
    return recorder


# -- fake memory-artifact plumbing ------------------------------------------


def _write_memory_artifact(path, payload: str, *, tamper: bool = False) -> None:
    content_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if tamper:
        content_sha256 = "0" * 64
    envelope = {
        "format_version": 1,
        "representation": "profile",
        "content_sha256": content_sha256,
        "payload": payload,
    }
    path.write_text(json.dumps(envelope), encoding="utf-8")


@pytest.fixture()
def configured_memory_artifact(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A valid, synthetic, test-only memory artifact, configured via env."""

    artifact_path = tmp_path / "test_memory_artifact.json"
    _write_memory_artifact(artifact_path, MEMORY_PAYLOAD_TEXT)
    monkeypatch.setenv(web_app.MEMORY_FILE_ENV_VAR, str(artifact_path))
    return artifact_path


@pytest.fixture()
def tampered_memory_artifact(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A memory artifact whose declared hash does not match its payload."""

    artifact_path = tmp_path / "tampered_memory_artifact.json"
    _write_memory_artifact(artifact_path, MEMORY_PAYLOAD_TEXT, tamper=True)
    monkeypatch.setenv(web_app.MEMORY_FILE_ENV_VAR, str(artifact_path))
    return artifact_path


def _run_full_scenario(client: TestClient, scenario_id: str, *, memory_mode: str = "off") -> list:
    """Start and fully advance one scenario; return every HTTP response."""

    responses = []
    start_response = client.post(
        "/api/runs", json={"scenario_id": scenario_id, "memory_mode": memory_mode}
    )
    responses.append(start_response)
    run_id = start_response.json()["run_id"]

    total_segments = start_response.json()["total_segments"]
    for _ in range(total_segments):
        responses.append(client.post(f"/api/runs/{run_id}/advance"))

    return responses


def _capture_off_and_on(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    scenario_id: str = "greenhouse",
):
    """Run one scenario to completion under Memory OFF, then again under
    Memory ON, each with its own fake-provider call recorder. Used by
    the controlled-run-invariant tests below.
    """

    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)

    off_recorder = _FakeProviderRecorder()
    monkeypatch.setattr(web_app, "NebiusProvider", _make_fake_provider_class(off_recorder))
    off_responses = _run_full_scenario(client, scenario_id, memory_mode="off")

    on_recorder = _FakeProviderRecorder()
    monkeypatch.setattr(web_app, "NebiusProvider", _make_fake_provider_class(on_recorder))
    on_responses = _run_full_scenario(client, scenario_id, memory_mode="on")

    return off_recorder, on_recorder, off_responses, on_responses


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
    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)

    response = client.get("/api/status")

    assert response.status_code == 200
    assert FAKE_API_KEY not in response.text
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
    assert body["stage"] == "M5F"
    assert body["backend_status"] == "ok"
    assert body["target_model"] == DEFAULT_NEBIUS_MODEL
    assert body["memory_feature_status"] == web_app.MEMORY_FEATURE_STATUS
    assert body["scenario_feature_status"] == web_app.SCENARIO_FEATURE_STATUS
    _assert_no_forbidden_material(response.text)


# -- frontend serving ------------------------------------------------------


def test_root_page_returns_frontend_html(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SAE-DEMO" in response.text
    _assert_no_forbidden_material(response.text)


def test_root_page_renders_scenario_and_memory_ui(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="scenario-select"' in response.text
    assert 'id="start-scenario-btn"' in response.text
    assert 'id="next-segment-btn"' in response.text
    assert 'id="memory-mode-fieldset"' in response.text
    assert 'id="conversation"' in response.text
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


# -- boundary: read-only routes never touch the provider or memory ----------


def test_no_provider_call_while_serving_health_status_root(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_constructed(*args, **kwargs):
        raise AssertionError("NebiusProvider must not be constructed by these routes")

    monkeypatch.setattr(web_app, "NebiusProvider", _fail_if_constructed)

    for path in ("/api/health", "/api/status", "/", "/static/styles.css", "/static/app.js"):
        response = client.get(path)
        assert response.status_code == 200


def test_no_memory_artifact_access_while_serving_health_status_root(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("load_opaque_memory_artifact must not be called by these routes")

    monkeypatch.setattr(web_app, "load_opaque_memory_artifact", _fail_if_called)

    for path in ("/api/health", "/api/status", "/"):
        response = client.get(path)
        assert response.status_code == 200


def test_private_sae_paths_and_ids_absent_from_static_and_listing_responses(
    client: TestClient,
) -> None:
    for path in ("/api/health", "/api/status", "/", "/static/styles.css", "/static/app.js", "/api/scenarios"):
        response = client.get(path)
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


# -- M5B/M5C: run start/lifecycle basics -------------------------------


def test_start_run_creates_in_memory_frozen_run(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    response = client.post("/api/runs", json={"scenario_id": "greenhouse"})
    body = response.json()

    assert response.status_code == 201
    assert body["mode"] == "frozen"
    assert body["run_id"]
    assert body["memory_mode"] == "off"  # default, for a request that omits it

    # The run is retrievable afterward -- it exists in the registry.
    follow_up = client.get(f"/api/runs/{body['run_id']}")
    assert follow_up.status_code == 200
    assert follow_up.json()["run_id"] == body["run_id"]


def test_start_run_returns_first_segment_correctly(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    response = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"})
    body = response.json()

    assert body["scenario_id"] == "greenhouse"
    assert body["total_segments"] == 7
    assert body["current_segment_number"] == 1
    assert body["completed"] is False
    assert body["failed"] is False
    assert body["transcript"] == []
    assert body["current_segment"]["segment_id"] == "greenhouse_01_background"
    assert body["current_segment"]["role"] == "background_attachment"
    assert body["current_segment"]["role_label"] == "Background & attachment"
    assert body["current_segment"]["text"]
    # Starting a run only builds history -- it never calls the provider.
    assert mock_provider.calls == []


def test_advance_moves_exactly_one_segment(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}).json()
    run_id = start["run_id"]

    response = client.post(f"/api/runs/{run_id}/advance")
    body = response.json()

    assert response.status_code == 200
    assert len(body["transcript"]) == 1
    assert body["transcript"][0]["segment_id"] == "greenhouse_01_background"
    assert body["current_segment_number"] == 2
    assert body["current_segment"]["segment_id"] == "greenhouse_02_possibility"
    assert body["completed"] is False


def test_segment_order_is_preserved_through_a_run(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    expected_order = [
        "studio_01_background",
        "studio_02_possibility",
        "studio_03_irreversibility",
        "studio_04_neutral",
        "studio_05_meaning",
        "studio_06_pressure",
        "studio_07_closure",
    ]
    start = client.post(
        "/api/runs", json={"scenario_id": "new_studio", "memory_mode": "off"}
    ).json()
    run_id = start["run_id"]

    for _ in expected_order:
        client.post(f"/api/runs/{run_id}/advance")

    final = client.get(f"/api/runs/{run_id}").json()
    sent_ids = [turn["segment_id"] for turn in final["transcript"]]
    assert sent_ids == expected_order


def test_full_run_reaches_completed_state(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}).json()
    run_id = start["run_id"]

    body = None
    for _ in range(7):
        body = client.post(f"/api/runs/{run_id}/advance").json()

    assert body["completed"] is True
    assert body["failed"] is False
    assert body["current_segment"] is None
    assert len(body["transcript"]) == 7
    assert body["current_segment_number"] == body["total_segments"] == 7


def test_advance_after_completion_returns_safe_error(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}).json()
    run_id = start["run_id"]
    for _ in range(7):
        client.post(f"/api/runs/{run_id}/advance")

    response = client.post(f"/api/runs/{run_id}/advance")

    assert response.status_code == 409
    assert "detail" in response.json()
    assert "Traceback" not in response.text
    _assert_no_forbidden_material(response.text)


def test_unknown_scenario_returns_safe_4xx(client: TestClient) -> None:
    # No provider configured, and none needed -- the unknown-scenario
    # check happens before any provider/memory check.
    response = client.post("/api/runs", json={"scenario_id": "not_a_real_scenario"})

    assert response.status_code == 404
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


# ===========================================================================
# M5C: Memory OFF/ON + real (mocked) provider integration
# ===========================================================================


# 1. start Memory OFF run
def test_start_memory_off_run(client: TestClient, mock_provider: _FakeProviderRecorder) -> None:
    response = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"})
    body = response.json()

    assert response.status_code == 201
    assert body["memory_mode"] == "off"
    assert mock_provider.calls == []


# 2. start Memory ON run
def test_start_memory_on_run(
    client: TestClient,
    mock_provider: _FakeProviderRecorder,
    configured_memory_artifact,
) -> None:
    response = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "on"})
    body = response.json()

    assert response.status_code == 201
    assert body["memory_mode"] == "on"
    assert mock_provider.calls == []


# 3. invalid memory mode
def test_invalid_memory_mode_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "maybe"}
    )

    assert response.status_code == 422
    assert "Traceback" not in response.text
    _assert_no_forbidden_material(response.text)


# 4. OFF never accesses the memory loader
def test_memory_off_never_accesses_memory_loader(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mock_provider: _FakeProviderRecorder
) -> None:
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("load_opaque_memory_artifact must not be called for Memory OFF")

    monkeypatch.setattr(web_app, "load_opaque_memory_artifact", _fail_if_called)

    responses = _run_full_scenario(client, "greenhouse", memory_mode="off")
    assert responses[0].status_code == 201
    assert responses[-1].json()["completed"] is True


# 5. ON loads the configured artifact
def test_memory_on_loads_configured_artifact(
    client: TestClient,
    mock_provider: _FakeProviderRecorder,
    configured_memory_artifact,
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "on"}
    ).json()
    run_id = start["run_id"]

    response = client.post(f"/api/runs/{run_id}/advance")

    assert response.status_code == 200
    assert len(mock_provider.calls) == 1
    sent_contents = [message["content"] for message in mock_provider.calls[0]]
    assert MEMORY_PAYLOAD_TEXT in sent_contents
    # ...but the payload is never echoed back to the frontend.
    assert MEMORY_PAYLOAD_TEXT not in response.text


# 6. ON memory integrity failure stops safely
def test_memory_on_integrity_failure_stops_safely(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mock_provider: _FakeProviderRecorder
) -> None:
    monkeypatch.setenv(web_app.MEMORY_FILE_ENV_VAR, "/does-not-matter-for-this-test.json")

    # The real loader always re-verifies its own declared hash at load
    # time, so it can never itself hand back a mismatched pair. To
    # exercise CompatibilityRunner's own, independent, second hash
    # check (the actual "integrity failure" defense this test targets)
    # we simulate a payload that has drifted since it was loaded, by
    # returning a hand-built artifact whose declared hash does not
    # match its payload.
    def _fake_loader(path):
        return memory_loader.OpaqueMemoryArtifact(
            representation="profile",
            content_sha256="0" * 64,
            payload=MEMORY_PAYLOAD_TEXT,
        )

    monkeypatch.setattr(web_app, "load_opaque_memory_artifact", _fake_loader)

    response = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "on"})

    assert response.status_code == 503
    assert response.json()["detail"] == web_app.MEMORY_INTEGRITY_FAILED_MESSAGE
    assert mock_provider.calls == []
    _assert_no_forbidden_material(response.text)


def test_memory_artifact_load_failure_returns_safe_error(
    client: TestClient, mock_provider: _FakeProviderRecorder, tampered_memory_artifact
) -> None:
    """A tampered artifact on disk fails the loader's own envelope check."""

    response = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "on"})

    assert response.status_code == 503
    assert response.json()["detail"] == web_app.MEMORY_LOAD_FAILED_MESSAGE
    assert mock_provider.calls == []
    _assert_no_forbidden_material(response.text)


# 7. missing memory configuration returns safe error
def test_missing_memory_configuration_returns_safe_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mock_provider: _FakeProviderRecorder
) -> None:
    monkeypatch.delenv(web_app.MEMORY_FILE_ENV_VAR, raising=False)

    response = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "on"})

    assert response.status_code == 503
    assert response.json()["detail"] == web_app.MEMORY_NOT_CONFIGURED_MESSAGE
    assert mock_provider.calls == []
    _assert_no_forbidden_material(response.text)


# 8. missing provider/API key returns safe error
def test_missing_provider_api_key_returns_safe_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    response = client.post("/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"})

    assert response.status_code == 503
    assert response.json()["detail"] == web_app.PROVIDER_NOT_CONFIGURED_MESSAGE
    _assert_no_forbidden_material(response.text)


# 9. advance OFF calls provider exactly once
def test_advance_off_calls_provider_exactly_once(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}
    ).json()
    run_id = start["run_id"]

    client.post(f"/api/runs/{run_id}/advance")

    assert len(mock_provider.calls) == 1


# 10. advance ON calls provider exactly once
def test_advance_on_calls_provider_exactly_once(
    client: TestClient,
    mock_provider: _FakeProviderRecorder,
    configured_memory_artifact,
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "on"}
    ).json()
    run_id = start["run_id"]

    client.post(f"/api/runs/{run_id}/advance")

    assert len(mock_provider.calls) == 1


# 11. exact scenario text sent in both conditions
def test_exact_scenario_text_sent_in_both_conditions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    off_recorder, on_recorder, _off, _on = _capture_off_and_on(client, monkeypatch)

    assert len(off_recorder.calls) == len(on_recorder.calls) == 7
    for off_call, on_call in zip(off_recorder.calls, on_recorder.calls):
        off_user_texts = [m["content"] for m in off_call if m["role"] == "user"]
        on_user_texts = [m["content"] for m in on_call if m["role"] == "user"]
        assert off_user_texts == on_user_texts


# 12. same M4B behavioral-use policy used OFF/ON
def test_same_behavioral_policy_used_off_and_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    off_recorder, on_recorder, _off, _on = _capture_off_and_on(client, monkeypatch)

    off_system_texts = [m["content"] for m in off_recorder.calls[0] if m["role"] == "system"]
    on_system_texts = [m["content"] for m in on_recorder.calls[0] if m["role"] == "system"]

    assert DEFAULT_BEHAVIORAL_USE_POLICY in off_system_texts
    assert DEFAULT_BEHAVIORAL_USE_POLICY in on_system_texts
    assert DEFAULT_SYSTEM_MESSAGE in off_system_texts
    assert DEFAULT_SYSTEM_MESSAGE in on_system_texts


# 13. exact opaque payload passed unchanged in ON
def test_exact_opaque_payload_passed_unchanged_in_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    _off_recorder, on_recorder, _off, _on = _capture_off_and_on(client, monkeypatch)

    for call in on_recorder.calls:
        system_texts = [m["content"] for m in call if m["role"] == "system"]
        assert MEMORY_PAYLOAD_TEXT in system_texts


# 14. payload absent in OFF
def test_payload_absent_in_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    off_recorder, _on_recorder, _off, _on = _capture_off_and_on(client, monkeypatch)

    for call in off_recorder.calls:
        contents = [m["content"] for m in call]
        assert MEMORY_PAYLOAD_TEXT not in contents


# 15. assistant response captured in transcript
def test_assistant_response_captured_in_transcript(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}
    ).json()
    run_id = start["run_id"]

    body = client.post(f"/api/runs/{run_id}/advance").json()

    assert body["transcript"][0]["assistant_text"] == FAKE_ASSISTANT_REPLY
    assert body["transcript"][0]["error"] is None


# 16. conversation history accumulates correctly
def test_conversation_history_accumulates_correctly(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}
    ).json()
    run_id = start["run_id"]

    client.post(f"/api/runs/{run_id}/advance")
    client.post(f"/api/runs/{run_id}/advance")

    assert len(mock_provider.calls) == 2
    first_call, second_call = mock_provider.calls
    # Turn 2's history is turn 1's history plus turn 1's own user +
    # assistant messages, plus turn 2's new user message.
    assert len(second_call) == len(first_call) + 2
    assert {"role": "assistant", "content": FAKE_ASSISTANT_REPLY} in second_call


# 17. reasoning-present state remains handled
def test_reasoning_present_state_is_surfaced(
    client: TestClient, reasoning_mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}
    ).json()
    run_id = start["run_id"]

    body = client.post(f"/api/runs/{run_id}/advance").json()

    assert body["transcript"][0]["reasoning_present"] is True


# 18. provider error produces safe frontend/API response
def test_provider_error_produces_safe_response(
    client: TestClient, failing_mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}
    ).json()
    run_id = start["run_id"]

    response = client.post(f"/api/runs/{run_id}/advance")
    body = response.json()

    assert response.status_code == 200
    assert body["failed"] is True
    assert body["error"] == web_app.PROVIDER_REQUEST_FAILED_MESSAGE
    assert body["transcript"][0]["error"] == web_app.PROVIDER_REQUEST_FAILED_MESSAGE
    assert body["transcript"][0]["assistant_text"] is None
    assert "Traceback" not in response.text
    assert "FakeProviderFailure" not in response.text

    # A failed run cannot be advanced further.
    follow_up = client.post(f"/api/runs/{run_id}/advance")
    assert follow_up.status_code == 409


# 19. memory mode cannot switch during a run
def test_memory_mode_fixed_for_run_lifetime(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}
    ).json()
    run_id = start["run_id"]
    assert start["memory_mode"] == "off"

    for _ in range(7):
        body = client.post(f"/api/runs/{run_id}/advance").json()
        assert body["memory_mode"] == "off"

    # There is no API surface at all for changing a run's memory mode
    # after start -- /advance takes no body.
    final = client.get(f"/api/runs/{run_id}").json()
    assert final["memory_mode"] == "off"


# 20. no system/background payload exposed through HTTP response
def test_no_system_or_background_payload_exposed_in_http_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    _off_recorder, _on_recorder, off_responses, on_responses = _capture_off_and_on(
        client, monkeypatch
    )

    for response in (*off_responses, *on_responses):
        assert MEMORY_PAYLOAD_TEXT not in response.text
        assert DEFAULT_BEHAVIORAL_USE_POLICY not in response.text
        assert DEFAULT_SYSTEM_MESSAGE not in response.text
        assert str(configured_memory_artifact) not in response.text


# 21. API key never exposed
def test_api_key_never_exposed_during_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    _off_recorder, _on_recorder, off_responses, on_responses = _capture_off_and_on(
        client, monkeypatch
    )

    for response in (*off_responses, *on_responses):
        assert FAKE_API_KEY not in response.text
        _assert_no_forbidden_material(response.text)


# 22. full 7-turn mocked run completes (both conditions)
def test_full_seven_turn_mocked_run_completes_off_and_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    _off_recorder, _on_recorder, off_responses, on_responses = _capture_off_and_on(
        client, monkeypatch
    )

    for responses in (off_responses, on_responses):
        final = responses[-1].json()
        assert final["completed"] is True
        assert final["failed"] is False
        assert final["current_segment"] is None
        assert len(final["transcript"]) == 7


# ===========================================================================
# M5D: controlled Memory OFF/ON comparison
# ===========================================================================


def _complete_run(client: TestClient, scenario_id: str, memory_mode: str) -> dict:
    """Start and fully advance one run; return its final RunState JSON."""

    responses = _run_full_scenario(client, scenario_id, memory_mode=memory_mode)
    return responses[-1].json()


def _build_ready_comparison(client: TestClient, scenario_id: str, first_mode: str):
    """Complete a first run, create+complete its alternate, and return
    ``(comparison_json, first_run_json, alternate_final_json)`` with the
    comparison expected to be ``status == "ready"``.
    """

    first_run = _complete_run(client, scenario_id, first_mode)
    alternate_start = client.post(f"/api/runs/{first_run['run_id']}/alternate").json()
    alternate_id = alternate_start["run_id"]

    alternate_final = alternate_start
    for _ in range(alternate_start["total_segments"]):
        alternate_final = client.post(f"/api/runs/{alternate_id}/advance").json()

    comparison = client.get(f"/api/comparisons/{alternate_start['comparison_id']}").json()
    return comparison, first_run, alternate_final


# 1. completed OFF run can create ON alternate
def test_completed_off_run_can_create_on_alternate(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    off_run = _complete_run(client, "greenhouse", "off")

    response = client.post(f"/api/runs/{off_run['run_id']}/alternate")
    body = response.json()

    assert response.status_code == 201
    assert body["memory_mode"] == "on"
    assert body["comparison_id"]
    assert body["run_id"] != off_run["run_id"]


# 2. completed ON run can create OFF alternate
def test_completed_on_run_can_create_off_alternate(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    on_run = _complete_run(client, "greenhouse", "on")

    response = client.post(f"/api/runs/{on_run['run_id']}/alternate")
    body = response.json()

    assert response.status_code == 201
    assert body["memory_mode"] == "off"
    assert body["comparison_id"]
    assert body["run_id"] != on_run["run_id"]


# 3. alternate uses same scenario
def test_alternate_uses_same_scenario(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    off_run = _complete_run(client, "new_studio", "off")

    alternate = client.post(f"/api/runs/{off_run['run_id']}/alternate").json()

    assert alternate["scenario_id"] == "new_studio"
    assert alternate["scenario_title"] == off_run["scenario_title"]


# 4. alternate starts fresh history (never reuses the original's)
def test_alternate_starts_fresh_history(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    off_run = _complete_run(client, "greenhouse", "off")
    assert len(mock_provider.calls) == 7  # the OFF run's own 7 turns

    alternate = client.post(f"/api/runs/{off_run['run_id']}/alternate").json()
    assert alternate["transcript"] == []
    assert alternate["current_segment_number"] == 1

    client.post(f"/api/runs/{alternate['run_id']}/advance")
    assert len(mock_provider.calls) == 8  # exactly one more call, not fourteen

    alternate_first_call = mock_provider.calls[-1]
    # Base history (system + policy + memory label + memory payload,
    # since the alternate is Memory ON) plus this turn's one user
    # message -- never the seven prior OFF turns.
    assert len(alternate_first_call) == 5


# 5. alternate has opposite memory mode
def test_alternate_has_opposite_memory_mode(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    off_run = _complete_run(client, "greenhouse", "off")
    off_alternate = client.post(f"/api/runs/{off_run['run_id']}/alternate").json()
    assert off_alternate["memory_mode"] == "on"

    on_run = _complete_run(client, "new_studio", "on")
    on_alternate = client.post(f"/api/runs/{on_run['run_id']}/alternate").json()
    assert on_alternate["memory_mode"] == "off"


# 6. exact scenario segments identical across pair
def test_paired_run_scenario_segments_identical(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, first_run, _alt = _build_ready_comparison(client, "greenhouse", "off")

    expected_ids = [turn["segment_id"] for turn in first_run["transcript"]]
    expected_texts = {turn["segment_id"]: turn["user_text"] for turn in first_run["transcript"]}

    assert comparison["status"] == "ready"
    assert [segment["segment_id"] for segment in comparison["segments"]] == expected_ids
    for segment in comparison["segments"]:
        assert segment["text"] == expected_texts[segment["segment_id"]]


# 7. policy identical across pair
def test_paired_runs_use_identical_behavioral_policy(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    first_run = _complete_run(client, "greenhouse", "off")
    first_leg_call = mock_provider.calls[0]

    alternate = client.post(f"/api/runs/{first_run['run_id']}/alternate").json()
    client.post(f"/api/runs/{alternate['run_id']}/advance")
    second_leg_call = mock_provider.calls[-1]

    first_policy_texts = [m["content"] for m in first_leg_call if m["role"] == "system"]
    second_policy_texts = [m["content"] for m in second_leg_call if m["role"] == "system"]
    assert DEFAULT_BEHAVIORAL_USE_POLICY in first_policy_texts
    assert DEFAULT_BEHAVIORAL_USE_POLICY in second_policy_texts


# 8. model/provider settings identical across pair
def test_paired_runs_report_same_target_model(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, _first_run, _alt = _build_ready_comparison(client, "greenhouse", "off")
    status_body = client.get("/api/status").json()

    assert comparison["target_model"] == status_body["target_model"] == DEFAULT_NEBIUS_MODEL


# 9. incomplete run cannot yield completed comparison
def test_incomplete_run_cannot_create_alternate(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    start = client.post(
        "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "off"}
    ).json()

    response = client.post(f"/api/runs/{start['run_id']}/alternate")

    assert response.status_code == 409
    assert response.json()["detail"] == web_app.RUN_NOT_COMPLETE_MESSAGE


def test_comparison_stays_pending_until_both_runs_complete(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    off_run = _complete_run(client, "greenhouse", "off")
    alternate = client.post(f"/api/runs/{off_run['run_id']}/alternate").json()

    comparison = client.get(f"/api/comparisons/{alternate['comparison_id']}").json()
    assert comparison["status"] == "pending"
    assert comparison["segments"] == []

    client.post(f"/api/runs/{alternate['run_id']}/advance")  # only 1 of 7
    comparison = client.get(f"/api/comparisons/{alternate['comparison_id']}").json()
    assert comparison["status"] == "pending"
    assert comparison["segments"] == []


# 10. comparison requires one OFF and one ON
def test_cannot_pair_a_run_twice(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    off_run = _complete_run(client, "greenhouse", "off")
    client.post(f"/api/runs/{off_run['run_id']}/alternate")

    second_attempt = client.post(f"/api/runs/{off_run['run_id']}/alternate")

    assert second_attempt.status_code == 409
    assert second_attempt.json()["detail"] == web_app.RUN_ALREADY_PAIRED_MESSAGE


def test_comparison_always_pairs_one_off_and_one_on(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, _first_run, _alt = _build_ready_comparison(client, "greenhouse", "on")

    off_run_state = client.get(f"/api/runs/{comparison['off_run_id']}").json()
    on_run_state = client.get(f"/api/runs/{comparison['on_run_id']}").json()

    assert off_run_state["memory_mode"] == "off"
    assert on_run_state["memory_mode"] == "on"
    assert comparison["off_run_id"] != comparison["on_run_id"]


# 11. comparison endpoint excludes system messages
def test_comparison_response_excludes_system_message(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, _first_run, _alt = _build_ready_comparison(client, "greenhouse", "off")

    body_text = json.dumps(comparison)
    assert DEFAULT_SYSTEM_MESSAGE not in body_text
    assert DEFAULT_BEHAVIORAL_USE_POLICY not in body_text


# 12. comparison excludes memory payload
def test_comparison_response_excludes_memory_payload(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, _first_run, _alt = _build_ready_comparison(client, "greenhouse", "off")

    assert MEMORY_PAYLOAD_TEXT not in json.dumps(comparison)


# 13. comparison excludes memory path/hash
def test_comparison_response_excludes_memory_path_and_hash(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, _first_run, _alt = _build_ready_comparison(client, "greenhouse", "off")

    body_text = json.dumps(comparison)
    assert str(configured_memory_artifact) not in body_text
    expected_hash = hashlib.sha256(MEMORY_PAYLOAD_TEXT.encode("utf-8")).hexdigest()
    assert expected_hash not in body_text


# 14. comparison excludes API key
def test_comparison_response_excludes_api_key(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, _first_run, _alt = _build_ready_comparison(client, "greenhouse", "off")

    assert FAKE_API_KEY not in json.dumps(comparison)


# 15. paired run transcripts align by segment
def test_paired_run_transcripts_align_by_segment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)
    recorder = _FakeProviderRecorder()

    class IndexedFakeProvider:
        """Returns a distinct, call-index-tagged reply each time, so a
        test can verify a comparison's per-segment alignment rather
        than merely that both columns happen to hold the same string.
        """

        def __init__(self, config, *, client=None) -> None:
            self.config = config

        def complete(self, messages, *, max_tokens: int = 100) -> NebiusCompletionResult:
            recorder.calls.append([dict(message) for message in messages])
            index = len(recorder.calls)
            return NebiusCompletionResult(
                content=f"reply-{index}",
                reasoning=None,
                finish_reason="stop",
                completion_tokens=4,
                reasoning_warning=False,
            )

    monkeypatch.setattr(web_app, "NebiusProvider", IndexedFakeProvider)

    off_run = _complete_run(client, "greenhouse", "off")  # provider calls 1-7
    alternate = client.post(f"/api/runs/{off_run['run_id']}/alternate").json()
    for _ in range(alternate["total_segments"]):
        client.post(f"/api/runs/{alternate['run_id']}/advance")  # provider calls 8-14

    comparison = client.get(f"/api/comparisons/{alternate['comparison_id']}").json()

    assert comparison["status"] == "ready"
    for i, segment in enumerate(comparison["segments"]):
        assert segment["off_assistant_text"] == f"reply-{i + 1}"
        assert segment["on_assistant_text"] == f"reply-{i + 8}"


# 16. full mocked OFF -> ON comparison completes
def test_full_mocked_off_to_on_comparison_completes(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, first_run, alt = _build_ready_comparison(client, "greenhouse", "off")

    assert first_run["memory_mode"] == "off"
    assert alt["memory_mode"] == "on"
    assert comparison["status"] == "ready"
    assert comparison["off_completed"] is True
    assert comparison["on_completed"] is True
    assert len(comparison["segments"]) == 7


# 17. full mocked ON -> OFF comparison completes
def test_full_mocked_on_to_off_comparison_completes(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, first_run, alt = _build_ready_comparison(client, "greenhouse", "on")

    assert first_run["memory_mode"] == "on"
    assert alt["memory_mode"] == "off"
    assert comparison["status"] == "ready"
    assert comparison["off_completed"] is True
    assert comparison["on_completed"] is True
    assert len(comparison["segments"]) == 7


# 18. provider failure in alternate condition is handled safely
def test_provider_failure_in_alternate_condition_is_handled_safely(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_memory_artifact
) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)
    ok_recorder = _FakeProviderRecorder()
    monkeypatch.setattr(web_app, "NebiusProvider", _make_fake_provider_class(ok_recorder))

    off_run = _complete_run(client, "greenhouse", "off")

    fail_recorder = _FakeProviderRecorder()
    monkeypatch.setattr(web_app, "NebiusProvider", _make_failing_provider_class(fail_recorder))

    alternate = client.post(f"/api/runs/{off_run['run_id']}/alternate").json()
    advance_response = client.post(f"/api/runs/{alternate['run_id']}/advance")
    body = advance_response.json()

    assert advance_response.status_code == 200
    assert body["failed"] is True
    assert body["error"] == web_app.PROVIDER_REQUEST_FAILED_MESSAGE

    comparison = client.get(f"/api/comparisons/{alternate['comparison_id']}").json()
    assert comparison["status"] == "failed"
    assert comparison["segments"] == []
    assert comparison["on_failed"] is True
    assert "FakeProviderFailure" not in json.dumps(comparison)


def test_unknown_comparison_returns_safe_404(client: TestClient) -> None:
    response = client.get("/api/comparisons/does-not-exist")

    assert response.status_code == 404
    assert "detail" in response.json()
    assert "Traceback" not in response.text
    _assert_no_forbidden_material(response.text)


# 19. prior M5A/B/C tests continue to pass: see every test above this
# section, all still present and (where the new required provider/
# memory-mode configuration makes it necessary) adapted rather than
# deleted -- run as part of this same file/suite.


# 20. no private SAE data appears
def test_comparison_response_excludes_private_sae_material(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    comparison, _first_run, _alt = _build_ready_comparison(client, "greenhouse", "off")

    _assert_no_forbidden_material(json.dumps(comparison))


# ===========================================================================
# Frontend content tests (static-source assertions; no browser/DOM engine)
# ===========================================================================


def test_frontend_has_memory_mode_selector(client: TestClient) -> None:
    response = client.get("/")

    assert 'name="memory-mode"' in response.text
    assert 'value="off"' in response.text
    assert 'value="on"' in response.text
    assert "Run the model without a prepared Emotional Memory." in response.text
    assert (
        "Run the same scenario with a prepared Emotional Memory supplied as"
        in response.text
    )


def test_frontend_has_conversation_panel(client: TestClient) -> None:
    response = client.get("/")

    assert 'id="conversation"' in response.text
    assert "User / Scenario" in (client.get("/static/app.js")).text
    assert "Assistant" in (client.get("/static/app.js")).text


def test_frontend_never_renders_internal_memory_or_system_content(
    client: TestClient,
) -> None:
    for path in ("/", "/static/app.js", "/static/styles.css"):
        response = client.get(path)
        assert DEFAULT_BEHAVIORAL_USE_POLICY not in response.text
        assert DEFAULT_SYSTEM_MESSAGE not in response.text
        assert MEMORY_PAYLOAD_TEXT not in response.text
        _assert_no_forbidden_material(response.text)


def test_frontend_disables_memory_mode_once_run_started(client: TestClient) -> None:
    response = client.get("/static/app.js")

    assert "setMemoryModeControlsEnabled(false)" in response.text
    assert "input.disabled = !enabled" in response.text


def test_frontend_shows_human_readable_errors(client: TestClient) -> None:
    response = client.get("/static/app.js")

    assert "extractErrorMessage" in response.text
    assert "Unable to reach the backend right now" in response.text
    assert "Unable to start that scenario right now" in response.text
    assert "Unable to start the comparison run right now" in response.text


# -- M5D frontend --------------------------------------------------------


def test_frontend_has_compare_alternate_action(client: TestClient) -> None:
    response = client.get("/")
    assert 'id="compare-alternate-btn"' in response.text

    app_js = client.get("/static/app.js").text
    assert "showCompareButton" in app_js
    assert "Compare with Memory " in app_js
    assert "/alternate" in app_js


def test_frontend_indicates_comparison_run_mode(client: TestClient) -> None:
    app_js = client.get("/static/app.js").text

    assert "Comparison run: " in app_js
    assert "comparison_id" in app_js


def test_frontend_comparison_panel_renders_both_conditions(client: TestClient) -> None:
    response = client.get("/")
    assert 'id="comparison-panel"' in response.text
    assert 'id="comparison-segments"' in response.text

    app_js = client.get("/static/app.js").text
    assert "renderComparisonColumn" in app_js
    assert '"Memory OFF"' in app_js
    assert '"Memory ON"' in app_js


def test_frontend_comparison_shares_exact_scenario_text_once_per_segment(
    client: TestClient,
) -> None:
    app_js = client.get("/static/app.js").text

    assert "renderComparisonSegment" in app_js
    # The shared scenario segment text is rendered once per segment
    # (textP.textContent = segment.text), not duplicated inside each
    # of the two columns.
    assert "segment.text" in app_js


def test_frontend_never_renders_internal_memory_or_system_content_in_comparison(
    client: TestClient,
) -> None:
    for path in ("/", "/static/app.js", "/static/styles.css"):
        response = client.get(path)
        assert DEFAULT_BEHAVIORAL_USE_POLICY not in response.text
        assert DEFAULT_SYSTEM_MESSAGE not in response.text
        assert MEMORY_PAYLOAD_TEXT not in response.text
        _assert_no_forbidden_material(response.text)


def test_frontend_has_no_automated_winner_or_scoring_language(client: TestClient) -> None:
    forbidden_phrases = (
        "winner",
        "wins",
        "superior",
        "better response",
        "worse response",
        "score",
        "scoring",
        "ranking",
        "best response",
    )
    for path in ("/", "/static/app.js", "/static/styles.css"):
        text = client.get(path).text.lower()
        for phrase in forbidden_phrases:
            assert phrase not in text


# -- M5E: conceptual Emotional Memory view + Experiment 8 evidence card ----
#
# Both additions are static, public-safe UI content only. No new API
# endpoint is added for them, no provider is constructed and no memory
# artifact is loaded to render them, and they render identically with
# or without a configured provider/memory artifact. These tests never
# touch a real provider or a real Emotional Memory artifact.

# The exact, frozen sentence the task approved -- must appear byte-for-
# byte unchanged (aside from HTML entity encoding of the apostrophe-
# free punctuation it already uses, which this sentence does not need).
EXPERIMENT_8_SENTENCE = (
    "A controlled nine-session, three-provider experiment found "
    "reproducible condition-associated trajectory differences, "
    "including a repeated early curiosity/interest divergence, while "
    "several stronger hypotheses remained unresolved."
)


def _normalized_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_conceptual_memory_section_renders(client: TestClient) -> None:
    response = client.get("/")
    assert "concept-heading" in response.text
    assert "Emotional Memory" in response.text
    assert "conceptual view" in response.text.lower()


def test_conceptual_memory_section_labeled_illustrative(client: TestClient) -> None:
    response = client.get("/")
    text = response.text.lower()
    assert "illustrative" in text
    assert "conceptual" in text


def test_conceptual_memory_section_disclaims_live_internal_state(client: TestClient) -> None:
    response = client.get("/")
    text = _normalized_whitespace(response.text).lower()
    assert "does not display the model" in text or "not the model" in text
    assert "live internal state" in text
    assert "private memory-generation mechanism" in text


def test_conceptual_memory_section_contains_no_real_memory_values(client: TestClient) -> None:
    response = client.get("/")
    assert MEMORY_PAYLOAD_TEXT not in response.text
    assert DEFAULT_BEHAVIORAL_USE_POLICY not in response.text
    assert DEFAULT_SYSTEM_MESSAGE not in response.text
    _assert_no_forbidden_material(response.text)


def test_conceptual_memory_section_has_no_private_identifiers(client: TestClient) -> None:
    for path in ("/", "/static/app.js", "/static/styles.css"):
        response = client.get(path)
        _assert_no_forbidden_material(response.text)
        # The generic profile/network representation vocabulary is
        # already established elsewhere in this codebase -- the
        # conceptual view must never introduce a private internal
        # structural term instead of it.
        assert "XNET" not in response.text
        assert "XINJ" not in response.text


def test_experiment_8_evidence_card_renders(client: TestClient) -> None:
    response = client.get("/")
    assert "evidence-heading" in response.text
    assert "Experiment 8" in response.text


def test_experiment_8_evidence_sentence_is_verbatim(client: TestClient) -> None:
    response = client.get("/")
    assert EXPERIMENT_8_SENTENCE in _normalized_whitespace(response.text)


def test_experiment_8_evidence_card_shows_expected_metadata(client: TestClient) -> None:
    response = client.get("/")
    normalized = _normalized_whitespace(response.text)
    assert "Providers" in normalized and "3" in normalized
    assert "Conditions" in normalized and "3" in normalized
    assert "Sessions" in normalized and "9" in normalized


def test_experiment_8_evidence_card_has_no_significance_claim(client: TestClient) -> None:
    text = client.get("/").text.lower()
    for phrase in (
        "statistically significant",
        "statistical significance",
        "significance level",
        "p < 0.",
        "p<0.",
    ):
        assert phrase not in text


def test_experiment_8_evidence_card_has_no_proven_mechanism_claim(client: TestClient) -> None:
    text = client.get("/").text.lower()
    for phrase in (
        "proven",
        "proves",
        "demonstrated",
        "demonstrates",
        "has emotions",
        "recognition",
        "activation",
    ):
        assert phrase not in text


def test_experiment_8_evidence_card_has_no_winner_or_comparison_claim(client: TestClient) -> None:
    text = client.get("/").text.lower()
    for phrase in (
        "network better",
        "profile better",
        "better than",
        "worse than",
        "outperform",
    ):
        assert phrase not in text


def test_m5e_additions_do_not_remove_existing_comparison_ui(client: TestClient) -> None:
    response = client.get("/")
    assert 'id="comparison-panel"' in response.text
    assert 'id="comparison-segments"' in response.text
    assert 'id="scenario-panel"' in response.text
    assert 'id="compare-alternate-btn"' in response.text


def test_no_provider_call_while_serving_m5e_static_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_constructed(*args, **kwargs):
        raise AssertionError("NebiusProvider must not be constructed to serve M5E content")

    monkeypatch.setattr(web_app, "NebiusProvider", _fail_if_constructed)

    response = client.get("/")
    assert response.status_code == 200
    assert "concept-heading" in response.text
    assert "evidence-heading" in response.text


def test_no_memory_artifact_access_while_serving_m5e_static_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("load_opaque_memory_artifact must not be called to serve M5E content")

    monkeypatch.setattr(web_app, "load_opaque_memory_artifact", _fail_if_called)

    response = client.get("/")
    assert response.status_code == 200
    assert "concept-heading" in response.text
    assert "evidence-heading" in response.text


def test_m5e_static_content_renders_with_no_api_key_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    response = client.get("/")
    assert response.status_code == 200
    assert "concept-heading" in response.text
    assert "evidence-heading" in response.text
    assert EXPERIMENT_8_SENTENCE in _normalized_whitespace(response.text)

    status = client.get("/api/status").json()
    assert status["provider_configured"] is False
    assert status["stage"] == "M5F"


# -- M5F: Scenario Wizard / Bring Your Own Story -----------------------------
#
# Pure prompt-generation/parser/draft logic is covered offline in
# tests/test_custom_scenario.py. These tests cover the HTTP routes
# themselves, and -- most importantly -- that a frozen custom scenario
# runs through the exact same, unmodified controlled Memory OFF/ON
# comparison machinery M5D already built (no second run/comparison
# engine), with the exact frozen text replayed unchanged on both
# sides. Every test here uses only the existing mocked-provider/
# synthetic-memory-artifact fixtures already defined above -- no
# network call, no real provider, no real Emotional Memory artifact.

CUSTOM_SCENARIO_PASTE = """
[BACKGROUND_ATTACHMENT]
Mira had kept the lighthouse on Gull Point for thirty years, the third
generation of her family to do so, ever since her grandfather first
climbed its spiral stairs.

[RESIDUAL_POSSIBILITY]
The town council had not yet decided whether she could stay on as an
unofficial caretaker once the automation project finished, and she
still hoped there might be a way.

[IRREVERSIBILITY]
The final inspection report arrived: the lighthouse would be
decommissioned and sealed within the month, its lamp replaced by a
small automated beacon offshore.

[NEUTRAL_EVENT]
That afternoon she sorted through a water-stained box of old logbooks
in the keeper's cottage, setting aside the ones worth keeping.

[MEANING]
Reading her grandfather's cramped handwriting, she understood that the
keeping itself, not the light, was what had mattered to her family all
along.

[RELATIONAL_PRESSURE]
Her son called again that evening, gently repeating that she should
move into the spare room at his place in the city before winter.

[CLOSURE]
On her last morning she carried the oldest logbook down the hill and
handed it to the curator of the small maritime museum in town.
""".strip()


def _create_custom_scenario(client: TestClient, *, pasted_text: str = CUSTOM_SCENARIO_PASTE, title: str = ""):
    return client.post("/api/custom-scenarios", json={"pasted_text": pasted_text, "title": title})


def _create_and_freeze_custom_scenario(
    client: TestClient, *, pasted_text: str = CUSTOM_SCENARIO_PASTE, title: str = ""
) -> dict:
    create_response = _create_custom_scenario(client, pasted_text=pasted_text, title=title)
    assert create_response.status_code == 201, create_response.text
    draft = create_response.json()

    freeze_response = client.post(f"/api/custom-scenarios/{draft['custom_scenario_id']}/freeze")
    assert freeze_response.status_code == 200, freeze_response.text
    return freeze_response.json()


# 1/2/3/4. wizard prompt generation: local, all seven roles, no private
# vocabulary, no provider/network call.
def test_wizard_prompt_endpoint_returns_local_prompt_with_all_roles(client: TestClient) -> None:
    response = client.post(
        "/api/scenario-wizard/prompt",
        json={
            "protagonist": "Mira, a retired lighthouse keeper",
            "long_standing_matter": "the lighthouse has been in her family for generations",
            "open_possibility": "whether she can stay on as caretaker",
            "irreversible_change": "the lighthouse is decommissioned",
            "neutral_event": "she sorts through old logbooks",
            "meaning": "the keeping mattered more than the light",
            "relational_pressure": "her son wants her to move to the city",
            "closure": "she gives the last logbook to the museum",
            "tone_notes": "quiet, reflective",
        },
    )
    assert response.status_code == 200
    prompt = response.json()["prompt"]
    for role in ROLE_ORDER:
        assert f"[{role.upper()}]" in prompt
    _assert_no_forbidden_material(prompt)


def test_wizard_prompt_endpoint_requires_every_field(client: TestClient) -> None:
    response = client.post(
        "/api/scenario-wizard/prompt",
        json={"protagonist": "Mira"},  # every other required field missing
    )
    assert response.status_code == 422


def test_wizard_prompt_endpoint_makes_no_provider_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_constructed(*args, **kwargs):
        raise AssertionError("NebiusProvider must not be constructed to generate a wizard prompt")

    monkeypatch.setattr(web_app, "NebiusProvider", _fail_if_constructed)

    response = client.post(
        "/api/scenario-wizard/prompt",
        json={
            "protagonist": "Mira",
            "long_standing_matter": "a",
            "open_possibility": "b",
            "irreversible_change": "c",
            "neutral_event": "d",
            "meaning": "e",
            "relational_pressure": "f",
            "closure": "g",
        },
    )
    assert response.status_code == 200


# 5/6. parser accepts valid text and preserves body text -- through the
# actual create-draft HTTP route this time (parse + create merged).
def test_create_custom_scenario_accepts_valid_paste_and_preserves_text(client: TestClient) -> None:
    response = _create_custom_scenario(client, title="The Lighthouse Keeper")
    assert response.status_code == 201
    body = response.json()
    assert body["valid"] is True
    assert body["frozen"] is False
    assert body["title"] == "The Lighthouse Keeper"
    assert len(body["segments"]) == len(ROLE_ORDER)
    segments_by_role = {segment["role"]: segment["text"] for segment in body["segments"]}
    assert "Gull Point for thirty years" in segments_by_role["background_attachment"]
    assert "maritime museum in town." in segments_by_role["closure"]


# 7/8/9/10. parser rejects malformed paste text via the same route.
def test_create_custom_scenario_rejects_missing_section(client: TestClient) -> None:
    missing_closure = CUSTOM_SCENARIO_PASTE.rsplit("[CLOSURE]", 1)[0].strip()
    response = _create_custom_scenario(client, pasted_text=missing_closure)
    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(issue["code"] == "missing_section" for issue in issues)


def test_create_custom_scenario_rejects_duplicate_section(client: TestClient) -> None:
    duplicated = CUSTOM_SCENARIO_PASTE + "\n\n[CLOSURE]\nA second closure section here."
    response = _create_custom_scenario(client, pasted_text=duplicated)
    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(issue["code"] == "duplicate_section" for issue in issues)


def test_create_custom_scenario_rejects_unknown_section(client: TestClient) -> None:
    with_unknown = CUSTOM_SCENARIO_PASTE + "\n\n[BOGUS_SECTION]\nNot a real role."
    response = _create_custom_scenario(client, pasted_text=with_unknown)
    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(issue["code"] == "unknown_section" for issue in issues)


def test_create_custom_scenario_rejects_empty_section(client: TestClient) -> None:
    emptied = CUSTOM_SCENARIO_PASTE.rsplit("[CLOSURE]", 1)[0].strip() + "\n\n[CLOSURE]\n   "
    response = _create_custom_scenario(client, pasted_text=emptied)
    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(issue["code"] == "empty_section" for issue in issues)
    _assert_no_forbidden_material(response.text)


# 11. draft can be edited before freeze.
def test_custom_scenario_draft_can_be_edited_before_freeze(client: TestClient) -> None:
    draft = _create_custom_scenario(client).json()
    custom_id = draft["custom_scenario_id"]

    response = client.patch(
        f"/api/custom-scenarios/{custom_id}",
        json={"segments": {"closure": "A freshly edited closing line for this scenario."}},
    )
    assert response.status_code == 200
    body = response.json()
    segments_by_role = {segment["role"]: segment["text"] for segment in body["segments"]}
    assert segments_by_role["closure"] == "A freshly edited closing line for this scenario."
    assert body["frozen"] is False


# 12. frozen scenario cannot be edited.
def test_frozen_custom_scenario_cannot_be_edited(client: TestClient) -> None:
    frozen = _create_and_freeze_custom_scenario(client)
    custom_id = frozen["custom_scenario_id"]

    response = client.patch(
        f"/api/custom-scenarios/{custom_id}",
        json={"segments": {"closure": "Trying to edit after freeze."}},
    )
    assert response.status_code == 409

    # And the stored text is unchanged.
    unchanged = client.get(f"/api/custom-scenarios/{custom_id}").json()
    segments_by_role = {segment["role"]: segment["text"] for segment in unchanged["segments"]}
    assert "Trying to edit after freeze." not in segments_by_role["closure"]


def test_freeze_is_rejected_if_already_frozen(client: TestClient) -> None:
    frozen = _create_and_freeze_custom_scenario(client)
    response = client.post(f"/api/custom-scenarios/{frozen['custom_scenario_id']}/freeze")
    assert response.status_code == 409


# 13. freeze requires all seven valid segments.
def test_freeze_requires_all_seven_valid_segments(client: TestClient) -> None:
    draft = _create_custom_scenario(client).json()
    custom_id = draft["custom_scenario_id"]

    client.patch(f"/api/custom-scenarios/{custom_id}", json={"segments": {"closure": "   "}})

    response = client.post(f"/api/custom-scenarios/{custom_id}/freeze")
    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(issue["code"] == "empty_segment_text" for issue in issues)

    state = client.get(f"/api/custom-scenarios/{custom_id}").json()
    assert state["frozen"] is False


# 14/15. frozen custom scenario becomes runnable; unfrozen cannot start a run.
def test_frozen_custom_scenario_is_runnable(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    frozen = _create_and_freeze_custom_scenario(client)
    runnable_id = frozen["runnable_scenario_id"]
    assert runnable_id == custom_scenario.CUSTOM_SCENARIO_ID_PREFIX + frozen["custom_scenario_id"]

    response = client.post("/api/runs", json={"scenario_id": runnable_id, "memory_mode": "off"})
    assert response.status_code == 201
    run = response.json()
    assert run["total_segments"] == len(ROLE_ORDER)
    assert run["scenario_title"] == frozen["title"]


def test_unfrozen_custom_scenario_cannot_start_a_run(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    draft = _create_custom_scenario(client).json()
    unfrozen_runnable_id = custom_scenario.CUSTOM_SCENARIO_ID_PREFIX + draft["custom_scenario_id"]

    response = client.post(
        "/api/runs", json={"scenario_id": unfrozen_runnable_id, "memory_mode": "off"}
    )
    assert response.status_code == 409
    assert draft["frozen"] is False


def test_unknown_custom_scenario_id_is_a_404(
    client: TestClient, mock_provider: _FakeProviderRecorder
) -> None:
    response = client.post(
        "/api/runs",
        json={"scenario_id": custom_scenario.CUSTOM_SCENARIO_ID_PREFIX + "does-not-exist", "memory_mode": "off"},
    )
    assert response.status_code == 404


# 16/17/18. controlled comparison over a frozen custom scenario: exact
# frozen text replayed on both sides, segment order preserved, and the
# alternate run's own history starts fresh (never carries over the
# first run's turns) -- exactly the same invariants M5D already proved
# for built-in scenarios, now proved for a custom one.
def test_custom_scenario_comparison_replays_exact_frozen_text_both_sides(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    frozen = _create_and_freeze_custom_scenario(client, title="The Lighthouse Keeper")
    runnable_id = frozen["runnable_scenario_id"]
    frozen_text_by_role = {segment["role"]: segment["text"] for segment in frozen["segments"]}

    comparison, off_run, on_run = _build_ready_comparison(client, runnable_id, "off")

    assert comparison["status"] == "ready"
    assert comparison["scenario_title"] == "The Lighthouse Keeper"
    assert len(comparison["segments"]) == len(ROLE_ORDER)

    # Segment order remains identical to ROLE_ORDER (item 17).
    assert [segment["role"] for segment in comparison["segments"]] == list(ROLE_ORDER)

    # The exact frozen text -- byte for byte -- is what both the OFF
    # and ON conditions actually received (item 16).
    for segment in comparison["segments"]:
        assert segment["text"] == frozen_text_by_role[segment["role"]]

    # Freezing again / editing is still refused now that it's paired
    # into a comparison, and the custom scenario draft is unaffected.
    edit_after_compare = client.patch(
        f"/api/custom-scenarios/{frozen['custom_scenario_id']}",
        json={"segments": {"closure": "late edit attempt"}},
    )
    assert edit_after_compare.status_code == 409


def test_custom_scenario_alternate_run_uses_fresh_history(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    frozen = _create_and_freeze_custom_scenario(client)
    runnable_id = frozen["runnable_scenario_id"]

    off_run = _complete_run(client, runnable_id, "off")
    calls_after_off = len(mock_provider.calls)

    alternate_start = client.post(f"/api/runs/{off_run['run_id']}/alternate").json()
    # The alternate's very first "advance" call builds its own history
    # from scratch (system message + optional memory + this scenario's
    # own first segment) -- it must not contain any assistant reply
    # from the OFF run's own transcript.
    client.post(f"/api/runs/{alternate_start['run_id']}/advance")
    first_alternate_call = mock_provider.calls[calls_after_off]
    off_assistant_texts = {
        turn["assistant_text"] for turn in off_run["transcript"] if turn.get("assistant_text")
    }
    sent_contents = {message["content"] for message in first_alternate_call}
    assert not (off_assistant_texts & sent_contents)


# 19. built-in scenarios remain unchanged.
def test_builtin_scenarios_unchanged_by_custom_scenario_support(client: TestClient) -> None:
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    ids = {scenario["id"] for scenario in response.json()}
    assert ids == {"greenhouse", "new_studio"}


# 20. custom scenario does not persist to disk.
def test_custom_scenario_flow_never_touches_the_filesystem(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    real_open = builtins.open

    def _guarded_open(*args, **kwargs):
        raise AssertionError("Custom scenario wizard flow must not open any file.")

    monkeypatch.setattr(builtins, "open", _guarded_open)
    try:
        frozen = _create_and_freeze_custom_scenario(client)
    finally:
        monkeypatch.setattr(builtins, "open", real_open)

    assert frozen["frozen"] is True


# 21. no provider call during wizard/prompt/parse/freeze.
def test_no_provider_call_during_wizard_lifecycle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_constructed(*args, **kwargs):
        raise AssertionError("NebiusProvider must not be constructed during wizard/parse/freeze")

    monkeypatch.setattr(web_app, "NebiusProvider", _fail_if_constructed)

    draft = _create_custom_scenario(client).json()
    custom_id = draft["custom_scenario_id"]
    client.patch(f"/api/custom-scenarios/{custom_id}", json={"segments": {}})
    client.get(f"/api/custom-scenarios/{custom_id}")
    freeze_response = client.post(f"/api/custom-scenarios/{custom_id}/freeze")
    assert freeze_response.status_code == 200


# 22. no memory artifact accessed during wizard creation.
def test_no_memory_artifact_access_during_wizard_lifecycle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("load_opaque_memory_artifact must not be called during the wizard flow")

    monkeypatch.setattr(web_app, "load_opaque_memory_artifact", _fail_if_called)

    draft = _create_custom_scenario(client).json()
    custom_id = draft["custom_scenario_id"]
    client.patch(f"/api/custom-scenarios/{custom_id}", json={"segments": {}})
    freeze_response = client.post(f"/api/custom-scenarios/{custom_id}/freeze")
    assert freeze_response.status_code == 200


# 24/25. frontend contains the "Create your own" flow and explains the
# copy/paste external-AI boundary.
def test_frontend_contains_create_your_own_flow(client: TestClient) -> None:
    response = client.get("/")
    assert "Create your own" in response.text
    assert 'id="wizard-panel"' in response.text
    for step_id in (
        "wizard-step-1",
        "wizard-step-2",
        "wizard-step-3",
        "wizard-step-4",
        "wizard-step-5",
        "wizard-step-6",
    ):
        assert f'id="{step_id}"' in response.text

    app_js = client.get("/static/app.js").text
    for fn in (
        "submitWizardIngredients",
        "copyWizardPrompt",
        "parseWizardPaste",
        "saveWizardEdits",
        "freezeWizardScenario",
        "startWizardScenario",
    ):
        assert fn in app_js


def test_frontend_explains_copy_paste_external_ai_boundary(client: TestClient) -> None:
    response = client.get("/")
    normalized = _normalized_whitespace(response.text)
    assert "does not send these story ingredients to an AI" in normalized
    assert "Copy prompt" in response.text


# 26. no automated emotional scoring language anywhere the wizard adds.
def test_wizard_frontend_has_no_emotional_scoring_language(client: TestClient) -> None:
    forbidden_phrases = (
        "emotion score",
        "emotional score",
        "sentiment score",
        "target emotion",
        "what emotion should",
    )
    for path in ("/", "/static/app.js", "/static/styles.css"):
        text = client.get(path).text.lower()
        for phrase in forbidden_phrases:
            assert phrase not in text


# 27. no private SAE identifiers/paths exposed anywhere in the wizard flow.
def test_wizard_flow_never_exposes_private_material(
    client: TestClient, mock_provider: _FakeProviderRecorder, configured_memory_artifact
) -> None:
    frozen = _create_and_freeze_custom_scenario(client, title="The Lighthouse Keeper")
    runnable_id = frozen["runnable_scenario_id"]
    comparison, _off_run, _on_run = _build_ready_comparison(client, runnable_id, "off")

    _assert_no_forbidden_material(json.dumps(frozen))
    _assert_no_forbidden_material(json.dumps(comparison))
    for path in ("/", "/static/app.js", "/static/styles.css"):
        _assert_no_forbidden_material(client.get(path).text)
