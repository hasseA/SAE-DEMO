"""Release-packaging coverage: the fresh-clone quick start works.

No network calls, no real provider, no real API key. These tests check
that the one approved Emotional Memory profile artifact is packaged at
a public, tracked location exactly as validated (never re-derived or
re-typed here -- everything is checked against the packaged file
itself, or against its pinned SHA-256), that `.env.example` and
`README.md` document the tested fresh-clone workflow, and that the
release default does not depend on a developer's local `.local/`
directory.

This module intentionally never references, packages, or asserts
anything about the network-representation artifact -- it is out of
scope for the current release per the private repository's M2.1
decision (see `docs/DISCLOSURE_BOUNDARY.md`, "Profile Emotional Memory
release status").
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sae_demo import memory_loader, web_app

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_MEMORY_DIR = REPO_ROOT / "demo_memory"
PACKAGED_PROFILE_PATH = DEMO_MEMORY_DIR / "despair_profile.json"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
README_PATH = REPO_ROOT / "README.md"

# Pinned from the exact, private-repo-approved artifact (M2.1 decision;
# see docs/DISCLOSURE_BOUNDARY.md, "Profile Emotional Memory release
# status"). These are hashes, not content -- nothing about the private
# creation method, or the artifact's own text, is reproduced here.
APPROVED_WHOLE_FILE_SHA256 = (
    "5b1e9cb66a2ee58a87af7c85d7cad5fc032a660ff09cc9e89efba0280d6cd44b"
)
APPROVED_CONTENT_SHA256 = (
    "ad659ae31004d3f54c0d96fbcb74f374d5674b75f37ff6ff0c3dacf545a9c1e2"
)

FAKE_API_KEY = "NEBIUS_API_KEY_VALUE_SHOULD_NEVER_APPEAR"

# Directories never walked when scanning tracked-shaped source for
# accidental network-artifact references -- these are exactly the
# categories `.gitignore` already keeps untracked (a developer's real
# `.local/` may legitimately contain the network artifact locally;
# that is expected and is not this test's concern).
_SKIP_DIR_NAMES = {
    ".git",
    ".local",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
}


def _iter_tracked_shaped_files():
    for root, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.endswith(".egg-info")]
        for filename in filenames:
            path = Path(root) / filename
            if path.suffix in {".pyc"}:
                continue
            yield path


# -- 1/2. the packaged artifact exists and is byte-identical ----------------


def test_packaged_profile_artifact_exists() -> None:
    assert PACKAGED_PROFILE_PATH.is_file()


def test_packaged_profile_artifact_sha256_matches_approved_source() -> None:
    import hashlib

    actual = hashlib.sha256(PACKAGED_PROFILE_PATH.read_bytes()).hexdigest()
    assert actual == APPROVED_WHOLE_FILE_SHA256


def test_packaged_profile_artifact_envelope_content_sha256_matches_approved() -> None:
    artifact = memory_loader.load_opaque_memory_artifact(PACKAGED_PROFILE_PATH)
    assert artifact.content_sha256 == APPROVED_CONTENT_SHA256
    assert artifact.representation == "profile"


# -- 3. .env.example points at the packaged artifact -------------------------


def test_env_example_points_to_packaged_artifact() -> None:
    text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    assert "SAE_DEMO_MEMORY_FILE=demo_memory/despair_profile.json" in text


# -- 4. the memory loader loads the packaged artifact -------------------------


def test_memory_loader_loads_packaged_artifact() -> None:
    artifact = memory_loader.load_opaque_memory_artifact(PACKAGED_PROFILE_PATH)
    assert isinstance(artifact.payload, str)
    assert len(artifact.payload) > 0


# -- 5. the release default does not depend on .local/ ------------------------


def test_env_example_default_memory_path_is_not_under_local_dir() -> None:
    text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("SAE_DEMO_MEMORY_FILE="):
            value = line.split("=", 1)[1].strip()
            assert not value.startswith(".local")
            return
    pytest.fail("SAE_DEMO_MEMORY_FILE is not set (uncommented) in .env.example")


def test_packaged_artifact_loads_without_any_local_dir_present(tmp_path, monkeypatch) -> None:
    # Point SAE_DEMO_LOCAL_DIR at a directory that does not exist and is
    # never created, proving the packaged artifact's own load path has
    # no dependency on `.local/` existing at all.
    monkeypatch.setenv("SAE_DEMO_LOCAL_DIR", str(tmp_path / "does-not-exist"))
    artifact = memory_loader.load_opaque_memory_artifact(PACKAGED_PROFILE_PATH)
    assert artifact.representation == "profile"


# -- 6. the network artifact is not packaged, referenced, or exposed --------


def test_network_artifact_not_packaged() -> None:
    assert DEMO_MEMORY_DIR.is_dir()
    packaged_names = {path.name for path in DEMO_MEMORY_DIR.iterdir() if path.is_file()}
    assert packaged_names == {"despair_profile.json"}


def test_network_artifact_not_referenced_in_tracked_shaped_source() -> None:
    # Built by concatenation, not as one literal, and this file itself is
    # skipped: this file's own source text necessarily contains the
    # needle once (right here) to describe what it is scanning for, and
    # that must not trip its own check -- mirrors the same pattern used
    # in tests/test_disclosure_guard.py for its synthetic secret string.
    this_file = Path(__file__).resolve()
    forbidden = "despair" + "_network"
    for path in _iter_tracked_shaped_files():
        if path.resolve() == this_file:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert forbidden not in text, f"unexpected reference in {path}"


# -- 7. no real API key in .env.example ---------------------------------------


def test_env_example_has_no_real_api_key() -> None:
    text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("NEBIUS_API_KEY="):
            assert line.strip() == "NEBIUS_API_KEY="
            return
    pytest.fail("NEBIUS_API_KEY line not found in .env.example")


# -- 8/9/10. README documents the tested workflow -----------------------------


def test_readme_contains_env_file_startup_flag() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    assert "--env-file .env" in text


def test_readme_explains_copying_env_example() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    assert "Copy-Item .env.example .env" in text
    assert "cp .env.example .env" in text


def test_readme_explains_user_provides_own_key() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    assert "your own Nebius API key" in text or "own Nebius API key" in text


def test_readme_describes_profile_memory_as_already_included() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    assert "approved, prepared Emotional Memory profile artifact" in text
    # Forbidden framings this section must never use.
    assert "generated on first run" not in text.lower()
    assert "the user must create it" not in text.lower()
    assert "creation method" not in text.lower() or "creation methodology" in text.lower()


# -- 11. a fresh-clone-like import succeeds ------------------------------------


def test_app_imports_cleanly_in_a_subprocess_with_no_api_key() -> None:
    env = dict(os.environ)
    env.pop("NEBIUS_API_KEY", None)
    result = subprocess.run(
        [sys.executable, "-c", "import sae_demo.web_app"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


# -- 12. health/status work without a real key ---------------------------------


def test_health_and_status_work_without_a_real_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    with TestClient(web_app.app) as client:
        health = client.get("/api/health")
        status = client.get("/api/status")

    assert health.status_code == 200
    assert status.status_code == 200
    assert status.json()["provider_configured"] is False


# -- 13. mocked Memory ON loads the packaged artifact --------------------------


class _RecordingFakeProvider:
    """No network call -- records every message list it was asked to
    complete, so this test can assert the packaged artifact's exact
    loaded payload was what got sent, without re-typing that payload
    anywhere in this file."""

    calls: list

    def __init__(self, config, *, client=None) -> None:
        self.config = config

    def complete(self, messages, *, max_tokens: int = 100):
        from sae_demo.nebius_provider import NebiusCompletionResult

        _RecordingFakeProvider.calls.append([dict(message) for message in messages])
        return NebiusCompletionResult(
            content="fake assistant reply (test double, not a real model output)",
            reasoning=None,
            finish_reason="stop",
            completion_tokens=8,
            reasoning_warning=False,
        )


def test_memory_on_loads_packaged_artifact_with_mocked_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEBIUS_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv(web_app.MEMORY_FILE_ENV_VAR, str(PACKAGED_PROFILE_PATH))
    _RecordingFakeProvider.calls = []
    monkeypatch.setattr(web_app, "NebiusProvider", _RecordingFakeProvider)

    expected_payload = memory_loader.load_opaque_memory_artifact(PACKAGED_PROFILE_PATH).payload

    with TestClient(web_app.app) as client:
        start = client.post(
            "/api/runs", json={"scenario_id": "greenhouse", "memory_mode": "on"}
        )
        assert start.status_code == 201
        run_id = start.json()["run_id"]

        response = client.post(f"/api/runs/{run_id}/advance")

    assert response.status_code == 200
    assert len(_RecordingFakeProvider.calls) == 1
    sent_contents = [message["content"] for message in _RecordingFakeProvider.calls[0]]
    assert expected_payload in sent_contents
    # The payload is never echoed back to the frontend.
    assert expected_payload not in response.text
