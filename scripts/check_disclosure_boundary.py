"""Disclosure/safety boundary checker — human-run, deterministic.

Safe to run before every commit (or before any future release work).
Read-only: makes no changes to the repository and does not inspect
Git history. Verifies:

  1. `.local/` is ignored by Git.
  2. `.env` is ignored by Git.
  3. No file under `.local/` is tracked.
  4. No `.env` file is tracked.
  5. No obvious API-key-like secret appears in tracked files.
  6. No path shaped like a future bounded-memory runtime artifact
     (`.local/memory/...`, `*.demo-memory.json`, `demo_memory/...`)
     is tracked -- except the one, single, explicitly-approved release
     artifact `demo_memory/despair_profile.json` (see the private
     repository's M2.1 decision and docs/RUNTIME_DATA_BOUNDARY.md,
     "The one tracked exception"). Any other path under `demo_memory/`
     still fails this check.

This is a lightweight guard, not a substitute for the manual
disclosure-boundary review described in docs/DISCLOSURE_BOUNDARY.md
and docs/RUNTIME_DATA_BOUNDARY.md (it does not, for example, detect
copied private SAE source or private conversation text).

Usage (from the repository root):

    python scripts/check_disclosure_boundary.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sae_demo.disclosure_guard import run_disclosure_checks_on_repo


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    report = run_disclosure_checks_on_repo(repo_root)

    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}")
        if result.detail:
            print(f"       {result.detail}")

    if report.passed:
        print("\nAll disclosure/safety checks passed.")
        return 0

    print("\nOne or more disclosure/safety checks FAILED. Review before committing.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
