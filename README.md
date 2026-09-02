# SAE-DEMO

A standalone Nebius hackathon project demonstrating SAE (Stable Emotion) Emotional Memory concepts against an NVIDIA model hosted through Nebius.

## Quick Start

The fastest path to a running demo, tested from a fresh clone.

**1. Get the code and enter the directory**

```
git clone <this repository>
cd SAE-DEMO
```

**2. Create and activate a virtual environment**

```
python -m venv .venv
```

PowerShell:

```
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```
source .venv/bin/activate
```

**3. Install runtime dependencies**

```
python -m pip install --upgrade pip
pip install -r requirements.txt
```

(Contributors running the test suite also need `pip install -r requirements-dev.txt`, which layers `pytest`/`httpx` on top of `requirements.txt` — not needed just to run the demo.)

**4. Create your `.env`**

PowerShell:

```
Copy-Item .env.example .env
notepad .env
```

macOS/Linux:

```
cp .env.example .env
```

Add your own Nebius API key; leave the rest as provided:

```
NEBIUS_API_KEY=YOUR_NEBIUS_API_KEY
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
SAE_DEMO_MEMORY_FILE=demo_memory/despair_profile.json
SAE_DEMO_MAX_TOKENS=400
SAE_DEMO_MAX_INFERENCE_CALLS_PER_CLIENT=20
SAE_DEMO_MAX_INFERENCE_CALLS_TOTAL=200
```

`.env` is gitignored and is never committed; `.env.example` never contains a real key. See "Key handling" below.

The demo includes one approved, prepared Emotional Memory profile artifact (`demo_memory/despair_profile.json`) — you don't need to create, generate, or locate anything yourself to try Memory ON. Leave `SAE_DEMO_MEMORY_FILE` as provided unless you intentionally want to point at a different, local artifact of your own (see "Opaque private-memory loader and Memory ON support" below).

**5. Start the server**

Start it with `--env-file .env` explicitly, so your key and settings are actually loaded — a plain `uvicorn` invocation without this flag will not see them.

PowerShell:

```
python -m uvicorn sae_demo.web_app:app `
  --host 127.0.0.1 `
  --port 8000 `
  --env-file .env
```

Single line (any shell):

```
python -m uvicorn sae_demo.web_app:app --host 127.0.0.1 --port 8000 --env-file .env
```

**6. Open the demo**

```
http://127.0.0.1:8000
```

**7. Try it**

- **Memory OFF** — pick a scenario, leave Memory OFF selected, and start a run.
- **Memory ON** — start a new run with Memory ON selected; it uses the included profile artifact automatically, no setup needed.
- **Controlled comparison** — once a run finishes, choose "Compare with Memory ON/OFF" to replay the same scenario under the opposite condition and see both transcripts side by side.
- **Optional — Create Your Own scenario** — choose "Create your own" under Scenario source to build and freeze a custom scenario with the Scenario Wizard, then run and compare it exactly like a built-in one (see "Scenario Wizard / Bring Your Own Story" below).

See "Local web demo" below for the full walkthrough of every step, and "Key handling" for what happens to your API key.

## Container / deployment preparation

The repository includes a minimal container definition for local validation.
Build it from the repository root:

```
docker build -t sae-demo .
```

Run it locally with configuration supplied at runtime from the same ignored
`.env` file described above:

```
docker run --rm -p 8000:8000 --env-file .env sae-demo
```

Then open `http://127.0.0.1:8000`. The container binds Uvicorn to `0.0.0.0`
and uses port `8000` by default. A deployment platform can override the
container port through `PORT`; for example, local port `8080` can be tested
with `docker run --rm -p 8080:8080 -e PORT=8080 --env-file .env sae-demo`.

Secrets are supplied only at container runtime. `.env` is excluded from the
Docker build context and is not copied into the image, and this repository does
not contain a Nebius API key. The image includes the approved
`demo_memory/despair_profile.json` at its existing runtime-relative path.

This is deployment preparation only. No hosted Nebius deployment has been
created or performed. Before making an inference-enabled instance publicly
reachable, follow `docs/PUBLIC_DEPLOYMENT_SAFETY.md`.

## Key handling

- You must provide your own Nebius API key — this project does not ship one and does not proxy or share a key.
- The key goes in your local `.env` file only.
- `.env` is gitignored and must never be committed.
- `.env.example` never contains a real key — only a blank placeholder and public-safe defaults.
- The key is used only server-side; it is never sent to the frontend and never appears in any API response (`/api/status` reports only whether a key is *present*, as a boolean).
- No secret manager or vault is used for this local hackathon demo — a local `.env` file is sufficient.

### Public-demo usage protection

The public demo has no password or login, so judges can open it and start
immediately. Process-local inference ceilings protect provider cost:
`SAE_DEMO_MAX_INFERENCE_CALLS_PER_CLIENT` defaults to `20` per server-issued
browser session and `SAE_DEMO_MAX_INFERENCE_CALLS_TOTAL` defaults to `200` for
the process. Failed provider attempts count, and all counters reset on server
restart. The Nebius API key remains server-side only. These are lightweight
hackathon-demo safeguards, not production authentication or a distributed
spending cap; an edge/platform rate limit and provider-side budget controls may
still be added during deployment. See `docs/PUBLIC_DEPLOYMENT_SAFETY.md`.

## Status

**Release packaging.** This repository now runs end to end from a fresh clone — see Quick Start above — with the one approved Emotional Memory profile artifact included at `demo_memory/despair_profile.json` and documented, tested startup instructions. Packaging only: no change to scenario architecture, the M4B consumption policy, provider/model configuration, or Emotional Memory content. **M5G: demo hardening and submission readiness.** A hardening-only pass — no new scenario, memory, or comparison capability was added. The per-turn completion-token budget (`max_tokens`) is now resolved from one configurable, environment-backed function (`compatibility_runner.resolve_max_tokens`, overridable via `SAE_DEMO_MAX_TOKENS`; default raised from 200 to 400) instead of a bare constant, still applied identically to Memory OFF and Memory ON through the single shared `_start_run_entry` call site — a modest, uniform increase meant to reduce live responses ending mid-sentence without giving either condition a different budget. `NebiusProvider.complete()` now treats a structurally unexpected (but HTTP-successful) response the same as a failed request — a safe, generic error, never an unhandled exception. The frontend gained a short "How to try it" walkthrough, a visible "Waiting for model…" state (plus a disabled-button guard against a duplicate request) for the one action that makes a real provider call, wording distinguishing scenario preparation from the controlled comparison, and a purely visual accent distinguishing the Memory OFF/ON comparison columns — assistant and scenario text continues to render as plain text with whitespace preserved, never as Markdown or raw HTML. See "Local web demo (M5A–M5G)" below and `docs/DEMO_READINESS_CHECKLIST.md` for the operational pre-submission checklist this stage adds. **M5F: Scenario Wizard / Bring Your Own Story added.** A "Create your own" scenario source now sits alongside the built-in scenarios: fill in a few plain-language story ingredients (protagonist plus one prompt per required semantic role, no target-emotion question), get back a locally generated, copyable AI prompt (`POST /api/scenario-wizard/prompt` — deterministic string templating only, no provider or network call), run that prompt through an AI you choose, and paste the resulting seven-section `[ROLE_NAME]`-bracketed story back (`POST /api/custom-scenarios`, which parses and validates in one step — an invalid paste creates nothing and returns its validation report instead of guessing). Review and edit every segment before freezing (`PATCH /api/custom-scenarios/{id}`); freezing (`POST /api/custom-scenarios/{id}/freeze`) requires all seven segments present and non-empty, and makes the text immutable from then on — the exact frozen text is what replays, unchanged, in both Memory OFF and Memory ON. A frozen custom scenario runs through the identical, unmodified M5D controlled-comparison flow a built-in scenario already used (the same `_start_run_entry`/`_resolve_scenario` resolution, the same `POST /api/runs`/`.../alternate`/`GET /api/comparisons/{id}`) — no second run or comparison engine exists for it. Custom scenario drafts are process-local and in-memory only, exactly like runs and comparisons; a server restart clears them, frozen or not. See "Local web demo (M5A–M5F)" below. **M5E: conceptual Emotional Memory view + Experiment 8 evidence card added.** The page now shows a small, static, clearly-labeled "Emotional Memory — conceptual view" diagram (purely illustrative/synthetic — not derived from, and not a rendering of, the real memory artifact, its internals, or any live model state) alongside a compact Experiment 8 evidence card carrying one fixed, approved sentence of research context plus simple metadata (3 providers, 3 conditions, 9 sessions). Both are static, public-safe UI content only — no new API endpoint was added, no provider is constructed and no memory artifact is loaded to render them, and they render identically with or without a configured provider or memory artifact. The controlled Memory OFF/ON comparison (M5D) remains the visually dominant part of the page; these additions sit below it. See "Local web demo (M5A–M5E)" below. **M5D: controlled Memory OFF/ON comparison added.** After a run completes, the same scenario can be replayed as a completely fresh run under the opposite memory condition (`POST /api/runs/{run_id}/alternate` — same scenario id, brand-new history, never reusing the first run's conversation); once both runs have finished, their transcripts are shown side by side, aligned by segment (`GET /api/comparisons/{comparison_id}`). A comparison is only ever built from a pair the app itself created this way — one completed Memory OFF run and one completed Memory ON run of the same scenario — never from two unrelated runs, and it is never shown as complete unless both sides actually finished successfully. The comparison performs no automated scoring, sentiment analysis, or "which response is better" judgment — it is only the two transcripts, for a person to read. Comparisons, like runs, are process-local and in-memory only. See "Local web demo (M5A–M5D)" below. **M5C: Memory OFF/ON web execution added.** The web app now connects the M5B scenario-run UI to a real assistant response on every "advance": pick Memory OFF or Memory ON before starting a run (fixed for that run's lifetime), and each segment sends through the existing, unchanged `NebiusProvider`, opaque memory loader, and M4B behavioral-use policy — no second implementation of memory placement/policy semantics exists; the web app drives the same `CompatibilityRunner.build_history()`/`send_turn()` methods `run()` itself uses. Memory ON uses exactly one operator-configured artifact, resolved from the `SAE_DEMO_MEMORY_FILE` environment variable — never a hardcoded path, and never a profile/network choice exposed in the UI. The exact memory payload stays opaque to the UI and is never returned in any API response; the provider API key stays backend-only. Runs remain process-local and in-memory (no persistence added). Side-by-side comparison of the two conditions is still a later M5 stage. See "Local web demo (M5A/M5B/M5C)" below. **M5B: scenario run UI added.** The web app now wires the existing, unchanged `ScenarioEngine` into a real scenario-run flow: pick `greenhouse` or `new_studio`, start a run, and advance segment by segment to a completed transcript. Runs are Memory OFF only, in-memory (a process-local registry, no database, no disk persistence), and reset on server restart. No provider call is made and no Emotional Memory artifact is touched — each segment's response area is labeled "Model response will appear in M5C" rather than showing any real or simulated model output. See "Local web demo (M5A/M5B)" below. **M5A: minimal FastAPI web shell added.** `sae_demo/web_app.py` serves a static vanilla HTML/CSS/JS frontend plus a typed `/api/health` and `/api/status` API. **M4: frozen.** The exact-memory consumption boundary reached across M3D -> M4A -> M4B is now recorded as an authoritative, frozen decision in `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md` (controlling IP boundary, evidence sequence, frozen policy text, and public/private claims boundary). M4B: extended the M4A behavioral-use policy's *text only* with one additional, generic scenario-grounding rule — concrete narrative details (people, places, events, objects, remembered scenes) in a response should stay grounded in the current conversation rather than be invented from background context, unless the user explicitly asks about that background context. No context placement, parameter, memory handling, or provider/model configuration changed; the opaque memory payload and its SHA-256 remain exactly as they were. M4A: added a generic, public-safe behavioral-use policy and a runtime payload-integrity check around the *unchanged* opaque memory payload. The Emotional Memory artifact itself is not modified, summarized, sanitized, or transformed in any way — only a new, independently-written consumption instruction and a hash re-check were added. The policy is sent identically for Memory OFF and Memory ON runs (see `docs/COMPATIBILITY_HARNESS.md`). M3D.1: fixed a Windows-only `UnicodeEncodeError` in the compatibility CLI's console output (`scripts/run_compatibility.py`), plus an associated mojibake risk, by reconfiguring stdout/stderr to UTF-8 (`sae_demo/console_io.py`) before printing. M3D: opaque private-memory artifact loader (`sae_demo/memory_loader.py`) and matching compatibility-runner memory-injection support added. The loader and runner have no knowledge of any private SAE schema — they validate/pass through a generic, versioned envelope (`format_version`, `representation`, `content_sha256`, `payload`) and treat `payload` as opaque text. No private artifact is ever tracked by Git; artifacts live only under the local, gitignored `.local/memory/` root. M3C.1: local-private runtime data boundary hardened — a single gitignored `.local/` root (`runs/`, `memory/`, `generated/`, `tmp/`), a generic runtime-path helper (`sae_demo/runtime_paths.py`), and a deterministic disclosure/safety checker (`sae_demo/disclosure_guard.py`, `scripts/check_disclosure_boundary.py`). M3C: synthetic compatibility runner implemented (`sae_demo/compatibility_runner.py`), supporting Memory OFF and, as of M3D, an opaque Memory ON path. M3B: backend scenario engine implemented. M3A: Nebius/NVIDIA provider transport layer implemented.

## What this project is

A small, independently built demo that lets a user compare an NVIDIA model's responses to a fixed scenario with an existing, bounded Emotional Memory representation supplied ("Memory ON") against the same scenario without it ("Memory OFF"), alongside a compact evidence card summarizing a conservative, already-published scientific result and a labeled conceptual visualization of the Emotional Memory idea.

## What Emotional Memory means here

At the level this demo needs, "Emotional Memory" is a bounded, already-prepared block of background context — organized from prior experience into things like attachment, unresolved possibility, salience, and relational orientation — that can be supplied to a model alongside a current scenario, so its response is shaped by that prior context rather than by the scenario alone. This demo treats one such artifact as an opaque input: it is inserted into the conversation exactly as given, never parsed, summarized, or transformed. The conceptual diagram on the page (see "Conceptual Emotional Memory view" in "Local web demo" below) illustrates that idea at a high level; it is not a rendering of the artifact's actual structure or of any live internal model state.

## What this demo does not disclose

This demo can use and demonstrate a real, working Emotional Memory artifact — the artifact's existence and its use as context are not treated as something to hide. What stays out of this project, always, is the private *method* that produces one: the extraction/derivation machinery, the structuring and weighting logic, the freezing/construction methodology, the private XNET/XINJ schema or implementation, any recognition or activation algorithm, and any model-adaptation/alignment technique. This repository also never discloses an API key, `.env` contents, or private scientific/provenance IDs. See `docs/DISCLOSURE_BOUNDARY.md` for the full operational rule.

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
- `docs/DEMO_READINESS_CHECKLIST.md` — operational, human-checked pre-submission checklist added in M5G

## Current limitations

- Runs, comparisons, and custom scenario drafts are process-local and in-memory only — there is no database and nothing is written to disk (outside the gitignored `.local/` root an operator may configure); a server restart clears all of them, frozen custom scenarios included.
- This registry design targets one operator, not concurrent multi-user access — the run/comparison lock serializes requests safely, but there is no per-user isolation.
- The Scenario Wizard's story authoring step is intentionally a copy/paste handoff to an external AI the user chooses; SAE-DEMO does not call one itself in this stage (see "Scenario Wizard / Bring Your Own Story" below for why).
- Live mid-run ("exploratory") editing of a scenario is not implemented; only the generate → paste → review → freeze → compare flow is.
- The completion-token budget is a fixed, operator-configurable value per process (`SAE_DEMO_MAX_TOKENS`) — it is not adjusted per scenario or per condition.
- This demo is not deployed publicly and has no remote configured; running it requires a local checkout and your own Nebius API key.

## Local web demo (M5A–M5G)

**Prerequisites:** Python 3.10+, a Nebius API key (see "Nebius/NVIDIA provider setup" below), and — only if you want to try Memory ON — a local, gitignored memory-artifact envelope. No `.env` or credential of any kind is ever committed to this repository; copy `.env.example` to `.env` and fill in your own values.

`sae_demo/web_app.py` is a minimal FastAPI application that serves the static frontend (`sae_demo/static/`) and exposes `/api/health`, `/api/status`, `/api/scenarios`, and the scenario-run endpoints below. `/api/status` reports only public-safe fields (application name, stage label, backend status, the public target-model identifier, whether a provider API key is *present* as a boolean, and static feature-status labels) — never the key's value, `.env` contents, filesystem paths, or any memory/private-SAE data.

**Scenario run UI (M5B) + Memory OFF/ON conversations (M5C).** The built-in synthetic scenarios (`greenhouse`, `new_studio` — the same two clean-room fixtures used by `scripts/run_compatibility.py` and the offline test suite) can be selected, started, and stepped through segment by segment in the browser, using the existing, unchanged `ScenarioEngine` in `frozen` mode. Before starting a run, choose Memory OFF or Memory ON; that choice is fixed for the run's lifetime (start a new run to try the other condition). Each "Next Segment" now sends the segment through the existing `CompatibilityRunner` (`NebiusProvider`, the M4B behavioral-use policy, and — for Memory ON — the one operator-configured, opaquely-loaded memory artifact) and shows the real assistant reply as a growing conversation. The UI never renders the memory payload, the system message, or the behavioral-use policy text — only each scenario segment's own text and the model's reply to it. Runs live only in a process-local, in-memory registry — there is no database and nothing is written to `.local/` or anywhere else on disk, so a server restart clears every in-progress run; this registry also does not attempt to solve multi-user or distributed concurrency, only safe concurrent access within one process.

See Quick Start above for the tested, end-to-end setup. In short: install runtime dependencies (`pip install -r requirements.txt`; add `requirements-dev.txt` only if you're also running the test suite), copy `.env.example` to `.env` and add your own `NEBIUS_API_KEY` — `SAE_DEMO_MEMORY_FILE` already points at the included, approved profile artifact, so Memory ON needs no further setup — then start the server with `--env-file .env` so `.env` is actually loaded (binds to localhost only):

```
python -m uvicorn sae_demo.web_app:app --host 127.0.0.1 --port 8000 --env-file .env
```

Then open `http://127.0.0.1:8000` in a browser. The page checks `/api/health` and `/api/status` on load and shows a connected/error indicator; pick Memory OFF or Memory ON, pick a scenario, and click "Start Scenario" to begin a run — if the provider (or, for Memory ON, the memory artifact) isn't configured, the page shows a clear, human-readable error and starts nothing. "Next Segment" advances the run one segment at a time, each time showing the real assistant response, to a completed conversation.

**Controlled comparison (M5D).** Once a run completes, the page offers "Compare with Memory ON" (or "Compare with Memory OFF", whichever is the opposite of the condition just run) as the prominent next action, alongside a less-prominent "Start a different scenario". Choosing it replays the *same* scenario as a completely fresh run — its own independent engine, provider call sequence, and conversation history, never reusing the first run's transcript — under the opposite memory condition; while that second run is in progress the page marks it clearly ("Comparison run: Memory ON" / "Comparison run: Memory OFF"). Once both runs have completed, the Comparison panel appears automatically: one row per scenario segment, the shared scenario text once, and the Memory OFF and Memory ON assistant replies side by side underneath it. The pairing is only ever between one completed Memory OFF run and one completed Memory ON run of that same scenario — never two unrelated runs, and never shown as complete while either side is still in progress or failed. The view shows the two transcripts as they are; it performs no automated scoring, sentiment analysis, or "which response is better" judgment of any kind. Comparisons, like runs, live only in a process-local, in-memory registry and are cleared on server restart.

**Conceptual Emotional Memory view + Experiment 8 evidence card (M5E).** Below the scenario/comparison experience, the page shows two small cards. The first, "Emotional Memory — conceptual view," is a static, synthetic diagram illustrating the idea that prior experience can shape a persistent emotional-memory layer that is present as background context alongside a current situation (Memory ON) versus absent (Memory OFF) — labeled "Illustrative model only," and explicitly not a rendering of the private memory-generation mechanism or any live internal model state; it is never read from, or derived from, a real memory artifact. The second, the Experiment 8 evidence card, carries one fixed sentence of already-approved research context plus simple metadata (3 providers, 3 conditions, 9 sessions) — no raw transcripts, internal identifiers, statistical-significance claims, or "proven"/"better than" claims of any kind. Neither card requires a configured provider or memory artifact to render, and neither performs any scoring, judging, or automated interpretation of the comparison above it.

**Scenario Wizard / Bring Your Own Story (M5F).** Choosing "Create your own" under Scenario source replaces the built-in scenario picker with a six-step flow. Step 1 collects a handful of plain-language ingredients (a protagonist, plus one prompt per required semantic role — never a "what emotion should the model feel" question); Step 2 shows a locally generated, copyable AI prompt built purely by local string templating (`POST /api/scenario-wizard/prompt`) — SAE-DEMO makes no provider or network call to produce it, and a note above Step 1 says plainly that the ingredients are not sent to an AI by SAE-DEMO itself. The user runs that prompt through any AI they trust, then pastes the seven-section `[ROLE_NAME]`-bracketed reply into Step 3; `POST /api/custom-scenarios` parses and validates it in one step, rejecting (with a specific, itemized report — never a silent guess or repair) a paste with a missing, duplicate, unknown, or empty section, or no recognizable headers at all. A valid paste opens Step 4, where all seven segments are shown in editable text areas (`PATCH /api/custom-scenarios/{id}`) until Step 5's "Freeze scenario for comparison" is used; freezing re-validates all seven segments, and once frozen the text can no longer be edited — the same scenario id then becomes available to Step 6's "Start Scenario", which drives the *exact same* `POST /api/runs`/`.../alternate`/`GET /api/comparisons/{id}` flow, and the *exact same* frontend rendering, that a built-in scenario already used. Custom scenario drafts (frozen or not) live only in a process-local, in-memory registry — never written to disk, and cleared on server restart, exactly like runs and comparisons. Live mid-run editing ("exploratory mode") is not part of this stage.

This copy/paste handoff — writing the story with an AI you trust, then pasting, reviewing, and freezing it here — is deliberate scenario preparation, not a missing feature: it is what guarantees the frozen text is byte-for-byte identical on both sides of the controlled comparison, without SAE-DEMO ever needing to call or trust any particular external AI itself.

**Demo hardening (M5G).** A short "How to try it" walkthrough sits at the top of the page, giving a first-time visitor the whole path (pick a scenario, choose Memory OFF/ON, run it, compare, then read the conceptual view and evidence card) in a few lines. The one action that makes a real provider call ("Next Segment") shows a visible "Waiting for model…" state and disables itself for the duration of that request, preventing a duplicate call from a fast double-click. The completion-token budget sent with every provider call is resolved once per run from `sae_demo/compatibility_runner.py`'s `resolve_max_tokens()` — the built-in default is 400 (raised from 200 to reduce real responses ending mid-sentence), overridable via `SAE_DEMO_MAX_TOKENS`, and always the same value for Memory OFF and Memory ON. `NebiusProvider` now converts a structurally malformed (but HTTP-successful) response into the same safe, generic error every other provider failure already produces, instead of letting an unexpected shape raise an unhandled exception. Assistant and scenario text is still rendered as plain text via `.textContent` with whitespace preserved (`white-space: pre-line`) — no Markdown rendering or raw HTML injection path was added. The comparison view's two columns get a purely visual left-border accent so Memory OFF and Memory ON are easier to tell apart at a glance; this carries no ranking or preference of either response. See `docs/DEMO_READINESS_CHECKLIST.md` for the operational checklist this stage adds ahead of a release/disclosure review.

## Nebius/NVIDIA provider setup (M3A)

The `sae_demo` package contains a minimal, independently written adapter for the Nebius Token Factory OpenAI-compatible API (`sae_demo/nebius_provider.py`), plus environment-based configuration loading (`sae_demo/config.py`).

Confirmed working configuration for this project:

- Base URL: `https://api.tokenfactory.nebius.com/v1/`
- Model: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
- Non-reasoning control (always sent by the provider): `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`

These are the package defaults; they can be overridden via environment variables if needed.

### Local setup

1. Copy `.env.example` to `.env` and fill in your own `NEBIUS_API_KEY`. `.env` is gitignored and must never be committed.
2. Install runtime dependencies: `pip install -r requirements.txt`. Also running the test suite additionally needs `pip install -r requirements-dev.txt` (layers `pytest`/`httpx` on top) — not required just to run the demo.
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

The demo includes one approved, prepared Emotional Memory profile artifact, tracked at `demo_memory/despair_profile.json` (see `docs/DISCLOSURE_BOUNDARY.md`, "Profile Emotional Memory release status"). It is the release default for `SAE_DEMO_MEMORY_FILE` (see `.env.example`), so the web demo's Memory ON path works from a fresh clone with no further setup. It is packaged exactly as approved — not generated, created, or derived by anything in this repository — and its SHA-256 is pinned by `tests/test_release_packaging.py` to catch any accidental change.

`scripts/run_compatibility.py` exposes this generically via `--memory {off,profile,network}` and `--memory-file PATH`. Neither the script nor any tracked source in this repository hardcodes the name, path, or content of any specific artifact — point `--memory-file` at any envelope file, including the packaged one:

```
python scripts/run_compatibility.py --fixture greenhouse --memory profile --memory-file demo_memory/despair_profile.json
python scripts/run_compatibility.py --fixture greenhouse --memory profile --memory-file .local/memory/<name>.json
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

All runtime-generated, non-public data — live run traces, provider outputs, generated scenario drafts, and any not-yet-approved bounded Emotional Memory artifact — belongs under a single gitignored root, `.local/` (`runs/`, `memory/`, `generated/`, `tmp/`), resolved by `sae_demo/runtime_paths.py` (default `<repo>/.local`, overridable via `SAE_DEMO_LOCAL_DIR`). Before committing, check the boundary:

```
python scripts/check_disclosure_boundary.py
```

See `docs/RUNTIME_DATA_BOUNDARY.md` for the full tracked-vs-local-only split, the rule this stage enforces (nothing originating from private SAE is Git-tracked in SAE-DEMO by default), and the one deliberate, narrowly-scoped tracked exception this release-packaging stage adds (`demo_memory/despair_profile.json`).

## License

SAE-DEMO is licensed under the Mozilla Public License 2.0 (MPL-2.0).
See `LICENSE`.

The approved `demo_memory/despair_profile.json` artifact is included as
part of this released work. The separate private SAE research repository
and unreleased Emotional Memory creation methodology are not included in
this repository or license grant.

Third-party services, models, dependencies, and trademarks remain subject
to their respective terms. No trademark rights are granted by the
MPL-2.0 license.
