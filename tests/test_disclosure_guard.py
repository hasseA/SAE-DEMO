"""Offline tests for the disclosure/safety boundary checker.

No network calls. Two layers are tested:

1. The pure `run_disclosure_checks()` function against synthetic,
   in-memory data (no Git involved at all).
2. `run_disclosure_checks_on_repo()` against a disposable, throwaway
   Git repository created fresh under pytest's own `tmp_path` for
   each test — never the real SAE-DEMO or SAE repository. This
   verifies the checker's real `git ls-files` / `git check-ignore`
   wiring without touching real Git state anywhere.
"""

import subprocess
from pathlib import Path

import pytest

from sae_demo.disclosure_guard import (
    run_disclosure_checks,
    run_disclosure_checks_on_repo,
)


# --- synthetic, in-memory data (no Git) -------------------------------------

def _clean_repo_shape():
    is_ignored = lambda path: path.startswith(".local") or path == ".env"
    tracked_paths = ["README.md", "sae_demo/scenario.py", "tests/test_scenario.py"]
    tracked_file_contents = [
        ("README.md", "# SAE-DEMO\n\nA hackathon project."),
        ("sae_demo/scenario.py", "class Scenario:\n    pass\n"),
        ("tests/test_scenario.py", "def test_x():\n    assert True\n"),
    ]
    return is_ignored, tracked_paths, tracked_file_contents


def test_checks_pass_on_synthetic_clean_repo_data():
    is_ignored, tracked_paths, tracked_file_contents = _clean_repo_shape()

    report = run_disclosure_checks(
        is_ignored=is_ignored,
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert report.passed
    assert report.failures() == ()


def test_checks_fail_when_local_dir_not_ignored():
    _, tracked_paths, tracked_file_contents = _clean_repo_shape()

    report = run_disclosure_checks(
        is_ignored=lambda path: path == ".env",  # .local NOT ignored
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert not report.passed
    assert "local_dir_ignored" in [f.name for f in report.failures()]


def test_checks_fail_when_env_not_ignored():
    _, tracked_paths, tracked_file_contents = _clean_repo_shape()

    report = run_disclosure_checks(
        is_ignored=lambda path: path.startswith(".local"),  # .env NOT ignored
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert not report.passed
    assert "env_ignored" in [f.name for f in report.failures()]


def test_checks_fail_on_tracked_local_file():
    is_ignored, tracked_paths, tracked_file_contents = _clean_repo_shape()
    tracked_paths = tracked_paths + [".local/runs/trace.json"]

    report = run_disclosure_checks(
        is_ignored=is_ignored,
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert not report.passed
    assert "no_local_files_tracked" in [f.name for f in report.failures()]


def test_checks_fail_on_tracked_env_file():
    is_ignored, tracked_paths, tracked_file_contents = _clean_repo_shape()
    tracked_paths = tracked_paths + [".env"]

    report = run_disclosure_checks(
        is_ignored=is_ignored,
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert not report.passed
    assert "no_env_file_tracked" in [f.name for f in report.failures()]


def test_checks_fail_on_secret_like_content():
    is_ignored, tracked_paths, tracked_file_contents = _clean_repo_shape()
    # Built by concatenation, not as one literal: this file's own source
    # text must never contain a literal secret-shaped string, or this
    # project's own disclosure_guard content scan would flag this test
    # file when scanning the real repository.
    fake_secret = "sk-" + "abcdefghijklmnop1234567890"
    tracked_file_contents = tracked_file_contents + [
        ("leaked.py", f'NEBIUS_API_KEY = "{fake_secret}"')
    ]

    report = run_disclosure_checks(
        is_ignored=is_ignored,
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert not report.passed
    failure = next(f for f in report.failures() if f.name == "no_secret_like_content")
    assert "leaked.py" in failure.detail


def test_checks_fail_on_tracked_bounded_memory_artifact():
    is_ignored, tracked_paths, tracked_file_contents = _clean_repo_shape()
    tracked_paths = tracked_paths + [".local/memory/export.json"]

    report = run_disclosure_checks(
        is_ignored=is_ignored,
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert not report.passed
    assert "no_bounded_memory_artifact_tracked" in [f.name for f in report.failures()]


def test_checks_fail_on_legacy_demo_memory_path_tracked():
    is_ignored, tracked_paths, tracked_file_contents = _clean_repo_shape()
    tracked_paths = tracked_paths + ["demo_memory/sample.json"]

    report = run_disclosure_checks(
        is_ignored=is_ignored,
        tracked_paths=tracked_paths,
        tracked_file_contents=tracked_file_contents,
    )

    assert not report.passed
    assert "no_bounded_memory_artifact_tracked" in [f.name for f in report.failures()]


# --- disposable, throwaway Git repository fixtures --------------------------

def _run_git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-q"], cwd=root)
    _run_git(["config", "user.name", "Test"], cwd=root)
    _run_git(["config", "user.email", "test@example.com"], cwd=root)


def _commit_all(root: Path, message: str) -> None:
    _run_git(["add", "-A"], cwd=root)
    _run_git(["commit", "-q", "-m", message], cwd=root)


@pytest.fixture
def clean_throwaway_repo(tmp_path) -> Path:
    """A disposable Git repo mirroring SAE-DEMO's real ignore/tracking shape.

    Created fresh under pytest's tmp_path for this test only; never
    touches the real SAE-DEMO or SAE repositories.
    """

    repo = tmp_path / "clean-repo"
    _init_repo(repo)

    (repo / ".gitignore").write_text(".local/\n.env\n.env.*\n!.env.example\n")
    (repo / "README.md").write_text("# Test project\n")
    (repo / "sae_demo").mkdir()
    (repo / "sae_demo" / "example.py").write_text("VALUE = 1\n")

    _commit_all(repo, "initial commit")
    return repo


def test_safety_checker_passes_on_a_clean_repo(clean_throwaway_repo):
    report = run_disclosure_checks_on_repo(clean_throwaway_repo)

    assert report.passed, report.failures()


def test_safety_checker_fails_on_force_tracked_env_file(tmp_path):
    repo = tmp_path / "bad-repo-env"
    _init_repo(repo)
    (repo / ".gitignore").write_text(".local/\n.env\n")
    (repo / "README.md").write_text("# Test project\n")
    (repo / ".env").write_text("NEBIUS_API_KEY=should-not-be-tracked\n")

    # Simulate an accidental force-add of a gitignored secret file.
    _run_git(["add", "-f", ".env", "README.md", ".gitignore"], cwd=repo)
    _run_git(["commit", "-q", "-m", "oops"], cwd=repo)

    report = run_disclosure_checks_on_repo(repo)

    assert not report.passed
    failure_names = [f.name for f in report.failures()]
    assert "no_env_file_tracked" in failure_names


def test_safety_checker_fails_on_force_tracked_local_runtime_file(tmp_path):
    repo = tmp_path / "bad-repo-local"
    _init_repo(repo)
    (repo / ".gitignore").write_text(".local/\n.env\n")
    (repo / "README.md").write_text("# Test project\n")
    local_dir = repo / ".local" / "runs"
    local_dir.mkdir(parents=True)
    (local_dir / "trace.json").write_text('{"segment": "a"}')

    # Simulate an accidental force-add of a gitignored runtime trace.
    _run_git(["add", "-f", ".local/runs/trace.json", "README.md", ".gitignore"], cwd=repo)
    _run_git(["commit", "-q", "-m", "oops"], cwd=repo)

    report = run_disclosure_checks_on_repo(repo)

    assert not report.passed
    failure_names = [f.name for f in report.failures()]
    assert "no_local_files_tracked" in failure_names
