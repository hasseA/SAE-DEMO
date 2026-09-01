"""Offline tests for the M5A FastAPI web shell (sae_demo/web_app.py).

No network calls, no provider calls, no Emotional Memory access. These
tests only exercise the health/status API and static frontend serving,
and assert that provider/memory functionality is never touched and
that no private material leaks into any HTTP response.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sae_demo import memory_loader, nebius_provider
from sae_demo.config import DEFAULT_NEBIUS_MODEL
from sae_demo.web_app import app

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
    assert body["stage"] == "M5A"
    assert body["backend_status"] == "ok"
    assert body["target_model"] == DEFAULT_NEBIUS_MODEL
    assert body["memory_feature_status"] == "not active in M5A"
    assert body["scenario_feature_status"] == "not active in M5A"
    _assert_no_forbidden_material(response.text)


# -- frontend serving ------------------------------------------------------


def test_root_page_returns_frontend_html(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SAE-DEMO" in response.text
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
        raise AssertionError("NebiusProvider must not be constructed by web_app in M5A")

    monkeypatch.setattr(
        nebius_provider.NebiusProvider, "__init__", _fail_if_constructed
    )

    for path in ("/api/health", "/api/status", "/", "/static/styles.css", "/static/app.js"):
        response = client.get(path)
        assert response.status_code == 200


def test_no_emotional_memory_artifact_is_accessed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(*args, **kwargs):
        raise AssertionError(
            "load_opaque_memory_artifact must not be called by web_app in M5A"
        )

    monkeypatch.setattr(
        memory_loader, "load_opaque_memory_artifact", _fail_if_called
    )

    for path in ("/api/health", "/api/status", "/"):
        response = client.get(path)
        assert response.status_code == 200


def test_private_sae_paths_and_ids_absent_from_all_responses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", "some-fake-value")

    for path in ("/api/health", "/api/status", "/", "/static/styles.css", "/static/app.js"):
        response = client.get(path)
        _assert_no_forbidden_material(response.text)
