"""Offline tests for the generic local-private runtime path helper.

No network calls, no real writes outside pytest's own tmp_path.
"""

from pathlib import Path

import pytest

from sae_demo.runtime_paths import (
    ENV_VAR,
    GENERATED,
    MEMORY,
    RUNS,
    TMP,
    ensure_dir,
    ensure_local_subdir,
    local_root,
    local_subdir,
)


def _repo_root() -> Path:
    # sae_demo/runtime_paths.py -> sae_demo/ -> repo root
    import sae_demo.runtime_paths as module

    return Path(module.__file__).resolve().parent.parent


def test_default_local_root_resolution():
    # env={} so an ambient SAE_DEMO_LOCAL_DIR in the real environment
    # (unlikely, but possible) can't affect this test.
    assert local_root(env={}) == _repo_root() / ".local"


def test_environment_override(tmp_path):
    custom = tmp_path / "somewhere-else"
    resolved = local_root(env={ENV_VAR: str(custom)})

    assert resolved == custom.resolve()
    assert resolved != _repo_root() / ".local"


def test_local_subdir_paths_under_root():
    for name in (RUNS, MEMORY, GENERATED, TMP):
        assert local_subdir(name, env={}) == _repo_root() / ".local" / name


def test_unknown_subdir_name_is_rejected():
    with pytest.raises(ValueError):
        local_subdir("not_a_real_subdir", env={})


def test_runtime_directories_created_only_when_requested(tmp_path):
    custom_root = tmp_path / "local-root"
    env = {ENV_VAR: str(custom_root)}

    # Resolving paths must not create anything on disk.
    assert local_root(env=env) == custom_root.resolve()
    assert not custom_root.exists()

    runs_dir = ensure_local_subdir(RUNS, env=env)

    assert runs_dir.is_dir()
    assert runs_dir == custom_root.resolve() / RUNS
    # Only the requested subdirectory was created — the others remain
    # untouched (lazy, per-subdirectory creation).
    for other in (MEMORY, GENERATED, TMP):
        assert not (custom_root.resolve() / other).exists()


def test_ensure_dir_is_idempotent(tmp_path):
    target = tmp_path / "a" / "b" / "c"

    first = ensure_dir(target)
    second = ensure_dir(target)

    assert first == second == target
    assert target.is_dir()
