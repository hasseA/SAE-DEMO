"""Generic local-private runtime path helper for SAE-DEMO.

Resolves a single local-only root directory (default `<repo>/.local`,
overridable via the `SAE_DEMO_LOCAL_DIR` environment variable) under
which all runtime-generated, non-public data lives: live compatibility
run traces, a future bounded Emotional Memory artifact, future
AI-generated scenario drafts, and temporary files.

This module is intentionally minimal and generic: it knows nothing
about the *contents* of any of that data, defines no schema for a
future Emotional Memory artifact, and never opens, reads, or inspects
any file. It only resolves paths and, when explicitly asked, creates
directories. Normal in-memory execution never needs to touch it — no
component in this project writes to `.local/` today.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional, Tuple

ENV_VAR = "SAE_DEMO_LOCAL_DIR"

# Named local-only subdirectories. Purely structural labels — this
# module defines no schema for what lives inside any of them.
RUNS = "runs"
MEMORY = "memory"
GENERATED = "generated"
TMP = "tmp"

SUBDIRS: Tuple[str, ...] = (RUNS, MEMORY, GENERATED, TMP)


def _repo_root() -> Path:
    # sae_demo/runtime_paths.py -> sae_demo/ -> repo root
    return Path(__file__).resolve().parent.parent


def local_root(env: Optional[Mapping[str, str]] = None) -> Path:
    """Resolve the local-private root directory.

    Defaults to `<repo>/.local`; overridable via `SAE_DEMO_LOCAL_DIR`
    (or an injectable `env` mapping, for testing). Does not create
    anything on disk — see `ensure_dir` / `ensure_local_subdir`.
    """

    source = env if env is not None else os.environ
    override = source.get(ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / ".local"


def local_subdir(name: str, *, env: Optional[Mapping[str, str]] = None) -> Path:
    """Resolve (but do not create) one named subdirectory under the local root."""

    if name not in SUBDIRS:
        raise ValueError(f"Unknown local subdirectory {name!r}. Valid names: {SUBDIRS}.")
    return local_root(env=env) / name


def ensure_dir(path: Path) -> Path:
    """Create `path` (and any missing parents) if needed, and return it.

    The only function in this module that touches the filesystem.
    Never called implicitly by any other function here — a caller
    opts in explicitly when it actually needs to write something.
    """

    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_local_subdir(name: str, *, env: Optional[Mapping[str, str]] = None) -> Path:
    """Resolve and create one named subdirectory under the local root."""

    return ensure_dir(local_subdir(name, env=env))
