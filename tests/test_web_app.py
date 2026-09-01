"""Offline tests for the FastAPI web shell (sae_demo/web_app.py).

No network calls, no real provider calls, no real Emotional Memory
artifact is ever read. M5A tests exercise the health/status API and
static frontend serving. M5B tests exercise scenario listing and the
in-memory scenario-run lifecycle. M5C tests exercise Memory OFF/ON
run configuration, the real (but always mocked-in-tests) provider
call made on each "advance", the controlled-run invariants that must
hold between Memory OFF and Memory ON, and the safe-error behavior
required when configuration or a provider call fails.

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

from sae_demo import memory_loader, web_app
from sae_demo.compatibility_runner import (
    DEFAULT_BEHAVIORAL_USE_POLICY,
    DEFAULT_SYSTEM_MESSAGE,
)
from sae_demo.config import DEFAULT_NEBIUS_MODEL
from sae_demo.nebius_provider import NebiusCompletionResult, NebiusProviderError
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
    assert body["stage"] == "M5C"
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
