# SAE-DEMO

A standalone Nebius hackathon project demonstrating SAE (Stable Emotion) Emotional Memory concepts against an NVIDIA model hosted through Nebius.

## Status

M3B: backend scenario engine implemented (`sae_demo/scenario.py`, `sae_demo/scenario_engine.py`), in-memory, with offline tests. M3A: Nebius/NVIDIA provider transport layer implemented (`sae_demo/config.py`, `sae_demo/nebius_provider.py`). No UI, conversation controller, Emotional Memory consumer, or Scenario Wizard exists yet — the scenario engine only loads and runs scenarios that are already fully written, and is not yet wired to the provider.

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
