# SAE-DEMO

A standalone Nebius hackathon project demonstrating SAE (Stable Emotion) Emotional Memory concepts against an NVIDIA model hosted through Nebius.

## Status

M3D: opaque private-memory artifact loader (`sae_demo/memory_loader.py`) and matching compatibility-runner memory-injection support added. The loader and runner have no knowledge of any private SAE schema — they validate/pass through a generic, versioned envelope (`format_version`, `representation`, `content_sha256`, `payload`) and treat `payload` as opaque text. No private artifact is ever tracked by Git; artifacts live only under the local, gitignored `.local/memory/` root. This stage does not run, and this repository does not contain, any live Memory ON/OFF comparison. M3C.1: local-private runtime data boundary hardened — a single gitignored `.local/` root (`runs/`, `memory/`, `generated/`, `tmp/`), a generic runtime-path helper (`sae_demo/runtime_paths.py`), and a deterministic disclosure/safety checker (`sae_demo/disclosure_guard.py`, `scripts/check_disclosure_boundary.py`). M3C: synthetic compatibility runner implemented (`sae_demo/compatibility_runner.py`), supporting Memory OFF and, as of M3D, an opaque Memory ON path. M3B: backend scenario engine implemented. M3A: Nebius/NVIDIA provider transport layer implemented. No UI or Scenario Wizard exists yet.

## What this project is

A small, independently built demo that lets a user compare an NVIDIA model's responses to a fixed scenario with an existing, bounded Emotional Memory representation supplied ("Memory ON") against the same scenario without it ("Memory OFF"), alongside a compact evidence card summarizing a conservative, already-published scientific result and a labeled conceptual visualization of the Emotional Memory idea.

## What this project is not

This is not the SAE research codebase, and it does not create, extract, or freeze Emotional Memory. It consumes one already-existing, bounded Emotional Memory export as an opaque external input. See `docs/DISCLOSURE_BOUNDARY.md` for what may and may not enter this repository, and `docs/PRODUCT_SPEC.md` / `docs/ARCHITECTURE.md` for the product and architecture this project targets.

## Relationship to the private SAE repository

SAE-DEMO is a clean-room project, independently implemented. It is not a fork, clone, filtered export, or copy of the private SAE research repository. Nothing in this repository was copied from that repository; where this repository needs to describe a concept from that research, it is described independently, in this project's own words.

## Documents

- `docs/PRODUCT_SPEC.md` — product purpose, user flow, MVP scope, explicit non-goals
- `docs/ARCHITECTURE.md` — component-level architecture for the independent demo, including the M3B scenario engine and the future Scenario Wizard boundary
- `docs/DISCLOSURE_BOUNDARY.md` — short operational rules for what may/may not enter this repository
- `docs/COMPATIBILITY_HARNESS.md` — what the compatibility runner is (and is not)
- `docs/RUNTIME_DATA_BOUNDARY.md` — the `.local/` runtime data boundary: what's tracked vs. local-only, and how it's checked

## Nebius/NVIDIA provider setup (M3A)

The `sae_demo` package contains a minimal, independently written adapter for the Nebius Token Factory OpenAI-compatible API (`sae_demo/nebius_provider.py`), plus environment-based configuration loading (`sae_demo/config.py`).

Confirmed working configuration for this project:

- Base URL: `https://api.tokenfactory.nebius.com/v1/`
- Model: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
- Non-reasoning control (always sent by the provider): `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`

These are the package defaults; they can be overridden via environment variables if needed.

### Local setup

1. Copy `.env.example` to `.env` and fill in your own `NEBIUS_API_KEY`. `.env` is gitignored and must never be committed.
2. Install dependencies: `pip install -r requirements-dev.txt`
3. Run the automated (offline, mocked, no network/API key required) test suite: `pytest`
4. Optionally run the manual live smoke test against the real API (uses your real key and incurs provider usage): `python scripts/smoke_nebius.py`

The provider treats any unexpected non-null `reasoning` field in a response as a configuration/safety warning rather than a fatal error, and logs a warning if one appears.

## Backend scenario engine (M3B)

`sae_demo/scenario.py` defines a clean-room, demo-specific scenario schema (id, title, ordered segments, per-segment semantic-role label and edit permission, `frozen`/`interactive` mode) with structural validation that reports every problem at once, for a future wizard UI to surface. `sae_demo/scenario_engine.py` loads one validated scenario in memory, exposes/advances its segments one at a time, supports editing a not-yet-sent segment in `interactive` mode while `frozen` mode preserves exact text for reproducible replay, and produces a neutral run trace recording exactly what text was sent per segment. The engine is independent of the Nebius provider adapter — attaching a model response to a sent segment happens after the fact via `record_model_response`, and the engine itself never makes a provider call.

Two entirely synthetic scenario fixtures (`tests/fixtures/synthetic_scenarios.py`) are used only to exercise the engine in offline tests; they are not sent to any model at this stage.

## Compatibility runner (M3C)

`sae_demo/compatibility_runner.py` (`CompatibilityRunner`) replays one **frozen** scenario through the M3A `NebiusProvider`, using the M3B `ScenarioEngine` to step through segments and a shared conversation history so each segment is sent as a user message with prior turns still in context. It records exact user/assistant text plus finish reason, model label, reasoning-field presence, and completion-token count for every turn — no emotional scoring or interpretation. See `docs/COMPATIBILITY_HARNESS.md` for the full scope statement.

### Running the live compatibility check locally

This makes real Nebius/NVIDIA API calls and is meant to be run by you, not automatically:

```
python scripts/run_compatibility.py --fixture greenhouse
python scripts/run_compatibility.py --fixture new_studio
python scripts/run_compatibility.py --fixture greenhouse --max-tokens 150
```

`--fixture` is required and selects one of the two built-in synthetic fixtures — no source edits needed to choose between them. By default this is a Memory OFF run.

## Opaque private-memory loader and Memory ON support (M3D)

`sae_demo/memory_loader.py` reads one local artifact envelope file — `{format_version, representation, content_sha256, payload}` — validates the envelope (supported version, recognized `representation` label, payload hash matches `content_sha256`), and returns `payload` as an opaque string. It has no knowledge of any private SAE schema and never parses, transforms, or interprets the payload content.

`CompatibilityRunner` accepts an optional `memory_payload` string; when supplied, it is inserted once, ahead of the scenario, as its own isolated, untouched message (preceded by a short, independently-written, generic label). With no `memory_payload` (the default), behavior is unchanged from M3C — Memory OFF.

`scripts/run_compatibility.py` exposes this generically via `--memory {off,profile,network}` and `--memory-file PATH`. Neither the script nor any tracked source in this repository hardcodes the name, path, or content of any specific artifact — a human operator must point `--memory-file` at a local, gitignored file themselves:

```
python scripts/run_compatibility.py --fixture greenhouse --memory profile --memory-file .local/memory/<name>.json
python scripts/run_compatibility.py --fixture greenhouse --memory network --memory-file .local/memory/<name>.json
```

No such run has been executed as part of this stage — this is implementation only. See `docs/RUNTIME_DATA_BOUNDARY.md` for where a private memory artifact lives (`.local/memory/`, gitignored, never tracked) and `tests/test_memory_loader.py` / the memory-injection tests in `tests/test_compatibility_runner.py` for the offline test coverage, all of which use only synthetic fake payloads.

## Runtime and local-private data boundary (M3C.1)

All runtime-generated, non-public data — live run traces, provider outputs, generated scenario drafts, and any bounded Emotional Memory artifact — belongs under a single gitignored root, `.local/` (`runs/`, `memory/`, `generated/`, `tmp/`), resolved by `sae_demo/runtime_paths.py` (default `<repo>/.local`, overridable via `SAE_DEMO_LOCAL_DIR`). Before committing, check the boundary:

```
python scripts/check_disclosure_boundary.py
```

See `docs/RUNTIME_DATA_BOUNDARY.md` for the full tracked-vs-local-only split and the rule this stage enforces: nothing originating from private SAE is Git-tracked in SAE-DEMO by default.
