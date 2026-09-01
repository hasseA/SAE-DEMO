# SAE-DEMO

A standalone Nebius hackathon project demonstrating SAE (Stable Emotion) Emotional Memory concepts against an NVIDIA model hosted through Nebius.

## Status

**M4: frozen.** The exact-memory consumption boundary reached across M3D -> M4A -> M4B is now recorded as an authoritative, frozen decision in `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md` (controlling IP boundary, evidence sequence, frozen policy text, and public/private claims boundary). M4B: extended the M4A behavioral-use policy's *text only* with one additional, generic scenario-grounding rule — concrete narrative details (people, places, events, objects, remembered scenes) in a response should stay grounded in the current conversation rather than be invented from background context, unless the user explicitly asks about that background context. No context placement, parameter, memory handling, or provider/model configuration changed; the opaque memory payload and its SHA-256 remain exactly as they were. M4A: added a generic, public-safe behavioral-use policy and a runtime payload-integrity check around the *unchanged* opaque memory payload. The Emotional Memory artifact itself is not modified, summarized, sanitized, or transformed in any way — only a new, independently-written consumption instruction and a hash re-check were added. The policy is sent identically for Memory OFF and Memory ON runs (see `docs/COMPATIBILITY_HARNESS.md`). M3D.1: fixed a Windows-only `UnicodeEncodeError` in the compatibility CLI's console output (`scripts/run_compatibility.py`), plus an associated mojibake risk, by reconfiguring stdout/stderr to UTF-8 (`sae_demo/console_io.py`) before printing. M3D: opaque private-memory artifact loader (`sae_demo/memory_loader.py`) and matching compatibility-runner memory-injection support added. The loader and runner have no knowledge of any private SAE schema — they validate/pass through a generic, versioned envelope (`format_version`, `representation`, `content_sha256`, `payload`) and treat `payload` as opaque text. No private artifact is ever tracked by Git; artifacts live only under the local, gitignored `.local/memory/` root. M3C.1: local-private runtime data boundary hardened — a single gitignored `.local/` root (`runs/`, `memory/`, `generated/`, `tmp/`), a generic runtime-path helper (`sae_demo/runtime_paths.py`), and a deterministic disclosure/safety checker (`sae_demo/disclosure_guard.py`, `scripts/check_disclosure_boundary.py`). M3C: synthetic compatibility runner implemented (`sae_demo/compatibility_runner.py`), supporting Memory OFF and, as of M3D, an opaque Memory ON path. M3B: backend scenario engine implemented. M3A: Nebius/NVIDIA provider transport layer implemented. No UI or Scenario Wizard exists yet.

## What this project is

A small, independently built demo that lets a user compare an NVIDIA model's responses to a fixed scenario with an existing, bounded Emotional Memory representation supplied ("Memory ON") against the same scenario without it ("Memory OFF"), alongside a compact evidence card summarizing a conservative, already-published scientific result and a labeled conceptual visualization of the Emotional Memory idea.

## What this project is not

This is not the SAE research codebase, and it does not create, extract, or freeze Emotional Memory. It consumes one already-existing Emotional Memory export as an opaque external input. See `docs/DISCLOSURE_BOUNDARY.md` for what may and may not enter this repository, and `docs/PRODUCT_SPEC.md` / `docs/ARCHITECTURE.md` for the product and architecture this project targets.

## Relationship to the private SAE repository

SAE-DEMO is a clean-room project, independently implemented. It is not a fork, clone, filtered export, or copy of the private SAE research repository. Nothing in this repository was copied from that repository; where this repository needs to describe a concept from that research, it is described independently, in this project's own words.

## Documents

- `docs/PRODUCT_SPEC.md` — product purpose, user flow, MVP scope, explicit non-goals
- `docs/ARCHITECTURE.md` — component-level architecture for the independent demo, including the M3B scenario engine and the future Scenario Wizard boundary
- `docs/DISCLOSURE_BOUNDARY.md` — short operational rules for what may/may not enter this repository
- `docs/COMPATIBILITY_HARNESS.md` — what the compatibility runner is (and is not), including the M4A/M4B Emotional Memory vs. behavioral-use-policy distinction
- `docs/RUNTIME_DATA_BOUNDARY.md` — the `.local/` runtime data boundary: what's tracked vs. local-only, and how it's checked
- `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md` — the frozen M4 consumption-boundary decision: controlling IP boundary, M3D -> M4A -> M4B evidence sequence, exact policy text, and allowed/prohibited claims

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

## Unicode console output on Windows (M3D.1)

A live compatibility run on Windows hit `UnicodeEncodeError` while printing an assistant response containing U+2011 NON-BREAKING HYPHEN, along with visibly garbled ("mojibake") punctuation elsewhere in the same terminal output. Root cause: Python's stdout/stderr default to the process's legacy ANSI code page on Windows (commonly cp1252), which cannot represent every valid Unicode character a model may return, and which can also produce mismatched (garbled) byte interpretation when text and the console's actual display encoding disagree.

`sae_demo/console_io.py` (`configure_utf8_stdio`) reconfigures stdout and stderr to UTF-8 in place, using the standard library's own `TextIOWrapper.reconfigure()`. `scripts/run_compatibility.py` calls it once, first thing in `main()`, before any output. This changes only how already-decoded text is *encoded on the way out* — it does not filter, escape, or ASCII-normalize model output, and it does not touch conversation history, memory injection, scenario content, or provider parameters. See `tests/test_console_io.py` for coverage including U+2011, a curly apostrophe, an em dash, and representative multi-script non-ASCII text, each verified to round-trip byte-for-byte through the reconfigured stream.

This fix makes the encoding step itself lossless and deterministic; it cannot guarantee how a legacy Windows console (e.g. `cmd.exe` without `chcp 65001`) chooses to *display* UTF-8 bytes on screen, which is a terminal/font concern outside this process's control. It does guarantee correct UTF-8 bytes for redirected/captured output (e.g. `... > run.txt`) and for terminals that read UTF-8 correctly (including modern Windows Terminal).

## Behavioral-use policy and payload integrity (M4A)

**Emotional Memory and the behavioral-use policy are two separate things.** Emotional Memory is the existing, prepared, opaque working representation loaded from `.local/memory/` — this project does not rewrite, summarize, sanitize, remove weights from, rename vocabulary in, or otherwise transform it in any way. It is not described here as merely a prompt; this project simply has no need to know, and does not inspect, what it structurally is.

The behavioral-use policy is a separate, short, generic, independently-written instruction (`sae_demo/compatibility_runner.DEFAULT_BEHAVIORAL_USE_POLICY`) telling the demo's consumer how to use *any* supplied background context in a response — it says nothing about what that context is or contains, mentions no private vocabulary, and adds no content of its own. It defaults to off at the `CompatibilityRunner` level (so no prior test or behavior changes unless a caller opts in), but `scripts/run_compatibility.py` sends it unconditionally and identically whether `--memory` is `off`, `profile`, or `network` — it is never a condition-specific difference, which keeps a future Memory OFF vs. Memory ON comparison from being confounded by this instruction only appearing on one side.

`scripts/run_compatibility.py` also passes the memory artifact's already loader-verified `content_sha256` through to `CompatibilityRunner`, which independently re-hashes the exact payload string immediately before it is placed into the conversation and refuses to send it (making no provider call) if the hash no longer matches — a defense-in-depth check, not a parse of the payload. See `docs/COMPATIBILITY_HARNESS.md` for the full architecture, and `tests/test_compatibility_runner.py` for the offline coverage (synthetic fake payloads only, including ones shaped with numbers/labels and unusual Unicode, to prove byte-for-byte pass-through).

## Scenario-grounding rule (M4B)

M3D's private testing showed that, even with M4A's anti-recitation rule in place, the model could still introduce concrete narrative details — people, places, events, objects, remembered scenes — that trace to background context rather than to the current conversation. **State may transfer; the source story should not be invented into the current story.**

M4B extends `DEFAULT_BEHAVIORAL_USE_POLICY`'s text with one additional sentence: background context may still shape interpretation, tone, and emotional or relational stance, but concrete details in a response should stay grounded in what the user has actually provided in the current conversation, unless the user explicitly asks about the background context. **This is a consumption-layer behavior rule. It does not modify Emotional Memory** — no context placement, parameter, memory handling, or provider/model configuration changed; the opaque payload and its SHA-256 are exactly as they were before this stage. See `docs/COMPATIBILITY_HARNESS.md` for the full rationale, and `tests/test_compatibility_runner.py` for the offline coverage (which checks the policy text and message structure only — whether a live model actually follows the rule is a separate, later, live test, deliberately out of scope here).

## M4 consumption boundary freeze

The controlling decision behind M4A/M4B, the full M3D -> M4A -> M4B evidence sequence, the frozen consumption architecture, and the public/private IP boundary are now recorded as an authoritative, frozen document: `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md`. Read it before proposing any change to Emotional Memory consumption, the behavioral-use policy text, or the payload-integrity mechanism.

## Runtime and local-private data boundary (M3C.1)

All runtime-generated, non-public data — live run traces, provider outputs, generated scenario drafts, and any bounded Emotional Memory artifact — belongs under a single gitignored root, `.local/` (`runs/`, `memory/`, `generated/`, `tmp/`), resolved by `sae_demo/runtime_paths.py` (default `<repo>/.local`, overridable via `SAE_DEMO_LOCAL_DIR`). Before committing, check the boundary:

```
python scripts/check_disclosure_boundary.py
```

See `docs/RUNTIME_DATA_BOUNDARY.md` for the full tracked-vs-local-only split and the rule this stage enforces: nothing originating from private SAE is Git-tracked in SAE-DEMO by default.
