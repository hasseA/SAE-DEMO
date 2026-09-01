# Runtime and Local-Private Data Boundary (M3C.1)

## The rule

**Nothing originating from private SAE is Git-tracked in SAE-DEMO by default.**

Everything this project generates at runtime — live model outputs, run traces, future generated scenario drafts, and a bounded Emotional Memory artifact — lives under one single, entirely gitignored local root, `.local/`, and stays off the record until someone deliberately decides otherwise.

## The `.local/` structure

```
.local/
    runs/       live compatibility traces and future session exports
    memory/     bounded Emotional Memory artifact(s), local-only
    generated/  future AI-generated scenario drafts / wizard output
    tmp/        temporary runtime files
```

`sae_demo/runtime_paths.py` resolves this root (default `<repo>/.local`, overridable via `SAE_DEMO_LOCAL_DIR`) and creates a named subdirectory only when a caller explicitly asks for one.

As of M3D, `.local/memory/` may legitimately contain one or more opaque memory-artifact envelope files (see `sae_demo/memory_loader.py`) prepared for a private compatibility check. This document does not describe, and this repository never tracks, what any such file's content is — only its generic envelope shape (`format_version`, `representation`, `content_sha256`, `payload`), which carries no information about how the payload was produced. Whether `.local/memory/` is empty or populated on a given machine has no bearing on what is or is not tracked by Git: the answer is always nothing.

## Tracked / public-safe

- Application source code (`sae_demo/`, `scripts/`), including the M3D opaque memory-artifact loader (`sae_demo/memory_loader.py`) and the compatibility runner's generic memory-injection support — both operate only on the envelope shape and never contain, reference, or depend on any specific artifact's content
- The two clean-room synthetic scenario fixtures (`tests/fixtures/synthetic_scenarios.py`) — these are original test definitions written for this project, not derived from private SAE material, so they remain ordinary tracked source
- Schemas/interfaces that are explicitly designed to be public-safe (e.g. the M3B scenario schema, the M3D opaque memory-artifact envelope shape)
- Tests, including `tests/test_memory_loader.py`, which uses only synthetic fake payloads
- Docs

## Local-only / gitignored

- API keys (`.env`)
- Live compatibility run traces and provider outputs
- Generated scenario drafts (future Scenario Wizard output)
- Bounded Emotional Memory artifact(s) under `.local/memory/`
- Other private compatibility artifacts
- Temporary comparison output

## On the bounded Emotional Memory artifact

A bounded Emotional Memory artifact is **local-only by default**. That is not a permanent prohibition on ever sharing it: it may become publishable only after a separate, explicit disclosure review and approval — the same kind of deliberate decision this project has applied to every other private/public boundary question so far. This document does not define, and this repository never tracks, any such artifact's format details, contents, or provenance beyond the generic envelope shape described above; `.local/memory/` is simply where it lives locally, gitignored, when and if it exists.

## Compatibility-runner persistence policy

The `CompatibilityRunner` returns its results in memory (`CompatibilityRunResult`) and does not write anything to disk. `scripts/run_compatibility.py` only prints to the terminal — this remains true with the M3D memory-selection flags (`--memory`, `--memory-file`): the artifact is read from wherever the caller points, and nothing about a run is written back to `.local/`. If a persistence feature is added later, it must write only under `.local/runs/`.

## Checking the boundary yourself

`scripts/check_disclosure_boundary.py` runs a small, deterministic, read-only set of checks against the real repository (does `git ls-files` show anything under `.local/` or named `.env`? does an obvious API-key-like pattern appear in a tracked file? is `.local/` actually ignored?) — see `sae_demo/disclosure_guard.py`. Run it before committing:

```
python scripts/check_disclosure_boundary.py
```

It is a lightweight guard, not a substitute for the manual review in `docs/DISCLOSURE_BOUNDARY.md` — it does not, for example, detect copied private SAE source or private conversation text. It never inspects Git history, never reads the contents of any file under `.local/`, and never modifies the repository.
