# Runtime and Local-Private Data Boundary (M3C.1)

## The rule

**Nothing originating from private SAE is Git-tracked in SAE-DEMO by default.**

Everything this project generates at runtime — live model outputs, run traces, future generated scenario drafts, and a future bounded Emotional Memory artifact — lives under one single, entirely gitignored local root, `.local/`, and stays off the record until someone deliberately decides otherwise.

## The `.local/` structure

```
.local/
    runs/       live compatibility traces and future session exports
    memory/     a future bounded Emotional Memory artifact
    generated/  future AI-generated scenario drafts / wizard output
    tmp/        temporary runtime files
```

`sae_demo/runtime_paths.py` resolves this root (default `<repo>/.local`, overridable via `SAE_DEMO_LOCAL_DIR`) and creates a named subdirectory only when a caller explicitly asks for one. Nothing in this project writes here today — the compatibility runner (M3C) works entirely in memory and has no save/export feature. This structure exists so that when persistence is eventually added, it has one obvious, already-protected place to write to, instead of that decision being made ad hoc under time pressure.

## Tracked / public-safe

- Application source code (`sae_demo/`, `scripts/`)
- The two clean-room synthetic scenario fixtures (`tests/fixtures/synthetic_scenarios.py`) — these are original test definitions written for this project, not derived from private SAE material, so they remain ordinary tracked source
- Schemas/interfaces that are explicitly designed to be public-safe (e.g. the M3B scenario schema)
- Tests
- Docs

## Local-only / gitignored

- API keys (`.env`)
- Live compatibility run traces and provider outputs
- Generated scenario drafts (future Scenario Wizard output)
- A future bounded Emotional Memory artifact
- Other private compatibility artifacts
- Temporary comparison output

## On the future bounded Emotional Memory artifact

A future bounded Emotional Memory artifact is **local-only by default**. That is not a permanent prohibition on ever sharing it: it may become publishable only after a separate, explicit disclosure review and approval — the same kind of deliberate decision this project has applied to every other private/public boundary question so far. Nothing in this stage defines that artifact's format, contents, or provenance; `.local/memory/` merely reserves where it would live locally if and when it exists.

## Compatibility-runner persistence policy

The M3C `CompatibilityRunner` returns its results in memory (`CompatibilityRunResult`) and does not write anything to disk. `scripts/run_compatibility.py` only prints to the terminal. This is intentional and unchanged by this stage: no export/save option was added merely to exercise `.local/runs/`. If a persistence feature is added later, it must write only under `.local/runs/`.

## Checking the boundary yourself

`scripts/check_disclosure_boundary.py` runs a small, deterministic, read-only set of checks against the real repository (does `git ls-files` show anything under `.local/` or named `.env`? does an obvious API-key-like pattern appear in a tracked file? is `.local/` actually ignored?) — see `sae_demo/disclosure_guard.py`. Run it before committing:

```
python scripts/check_disclosure_boundary.py
```

It is a lightweight guard, not a substitute for the manual review in `docs/DISCLOSURE_BOUNDARY.md` — it does not, for example, detect copied private SAE source or private conversation text. It never inspects Git history and never modifies the repository.
