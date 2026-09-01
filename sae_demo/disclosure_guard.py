"""Git-based disclosure/safety boundary checker for SAE-DEMO.

Deterministic, read-only checks over the current Git working tree:
confirms `.local/` and `.env` are ignored, confirms no tracked file
lives under `.local/` or is named `.env`, scans tracked file content
for obvious API-key-like secret patterns, and confirms no path shaped
like a bounded Emotional Memory artifact is tracked. Makes no changes
to the repository and never inspects Git history.

The individual checks are pure functions over plain data (a
"is this path ignored" predicate, a list of tracked paths, tracked
file contents) so they can be exercised offline against synthetic or
mocked data in tests, without requiring — or risking — a real Git
repository. `run_disclosure_checks_on_repo` wires that same logic to
a real repository via `git check-ignore` / `git ls-files` for
interactive/CLI use.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

# Secret-like patterns. Deliberately conservative (a handful of
# well-known shapes) rather than an exhaustive scanner — this is a
# lightweight guard, not a substitute for careful review.
_SECRET_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"sk-[a-zA-Z0-9]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)api[_-]?key\s*=\s*['\"][a-zA-Z0-9]{8,}"),
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9]{16,}"),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class DisclosureReport:
    results: Tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def failures(self) -> Tuple[CheckResult, ...]:
        return tuple(result for result in self.results if not result.passed)


# --- individual checks (pure functions over plain data) --------------------


def check_local_dir_ignored(is_ignored: Callable[[str], bool]) -> CheckResult:
    ok = is_ignored(".local/probe-file")
    return CheckResult("local_dir_ignored", ok, "" if ok else ".local/ is not ignored by Git.")


def check_env_ignored(is_ignored: Callable[[str], bool]) -> CheckResult:
    ok = is_ignored(".env")
    return CheckResult("env_ignored", ok, "" if ok else ".env is not ignored by Git.")


def check_no_local_files_tracked(tracked_paths: Sequence[str]) -> CheckResult:
    offending = [p for p in tracked_paths if p == ".local" or p.startswith(".local/")]
    ok = not offending
    detail = "" if ok else f"Tracked file(s) under .local/: {offending}"
    return CheckResult("no_local_files_tracked", ok, detail)


def check_no_env_file_tracked(tracked_paths: Sequence[str]) -> CheckResult:
    offending = [p for p in tracked_paths if p == ".env" or p.endswith("/.env")]
    ok = not offending
    detail = "" if ok else f"Tracked .env file(s): {offending}"
    return CheckResult("no_env_file_tracked", ok, detail)


def check_no_secret_like_content(
    tracked_file_contents: Iterable[Tuple[str, Optional[str]]]
) -> CheckResult:
    """`tracked_file_contents` is an iterable of (path, text_or_None) pairs."""

    offending: List[str] = []
    for path, text in tracked_file_contents:
        if not text:
            continue
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                offending.append(path)
                break
    ok = not offending
    detail = "" if ok else f"Possible secret-like content in: {offending}"
    return CheckResult("no_secret_like_content", ok, detail)


def check_no_bounded_memory_artifact_tracked(tracked_paths: Sequence[str]) -> CheckResult:
    offending = [
        p
        for p in tracked_paths
        if p.startswith(".local/memory/")
        or p.endswith(".demo-memory.json")
        or p == "demo_memory"
        or p.startswith("demo_memory/")
    ]
    ok = not offending
    detail = "" if ok else f"Tracked bounded-memory-artifact-shaped path(s): {offending}"
    return CheckResult("no_bounded_memory_artifact_tracked", ok, detail)


def run_disclosure_checks(
    *,
    is_ignored: Callable[[str], bool],
    tracked_paths: Sequence[str],
    tracked_file_contents: Iterable[Tuple[str, Optional[str]]],
) -> DisclosureReport:
    """Run every check against the given (possibly synthetic) inputs."""

    results = (
        check_local_dir_ignored(is_ignored),
        check_env_ignored(is_ignored),
        check_no_local_files_tracked(tracked_paths),
        check_no_env_file_tracked(tracked_paths),
        check_no_secret_like_content(tracked_file_contents),
        check_no_bounded_memory_artifact_tracked(tracked_paths),
    )
    return DisclosureReport(results)


# --- real-repository wiring (used by the CLI, not required for tests) ------


def _git_ls_files(repo_root: Path) -> List[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _git_is_ignored(path: str, repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=repo_root,
        capture_output=True,
    )
    return result.returncode == 0


def _read_tracked_file_text(repo_root: Path, path: str) -> Optional[str]:
    try:
        return (repo_root / path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def run_disclosure_checks_on_repo(repo_root: Path) -> DisclosureReport:
    """Run every check against the real Git repository at `repo_root`.

    Read-only: uses `git ls-files` and `git check-ignore` only, never
    inspects history, and makes no changes to the repository.
    """

    tracked = _git_ls_files(repo_root)
    contents = ((path, _read_tracked_file_text(repo_root, path)) for path in tracked)

    return run_disclosure_checks(
        is_ignored=lambda path: _git_is_ignored(path, repo_root),
        tracked_paths=tracked,
        tracked_file_contents=contents,
    )
