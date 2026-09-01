# M5 — Hackathon Demo UI/API Specification

Status: **design only**. Nothing in this document has been implemented. No frontend, backend, or API code exists yet beyond what M3A–M3D/M4A/M4B already built (`sae_demo/scenario.py`, `scenario_engine.py`, `nebius_provider.py`, `config.py`, `compatibility_runner.py`, `memory_loader.py`). This document specifies the smallest compelling demo that can be built around that existing backend without redesigning SAE or expanding scope beyond what a hackathon judge needs to see. It builds directly on the frozen boundary in `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md` and does not reopen it.

## 1. M5 objective

Give a hackathon judge or user a small, self-contained web demo that runs the same synthetic scenario twice against the same NVIDIA/Nebius model — once with no Emotional Memory supplied ("Memory OFF") and once with an existing, prepared Emotional Memory export supplied ("Memory ON") — and lets them watch the responses unfold segment by segment and compare the two runs, without needing to read any research documentation first.

## 2. User story

As a hackathon judge, I open a link, pick a scenario, choose Memory OFF or Memory ON, and watch the model respond to a short story one piece at a time. When the run finishes, I can trigger the same scenario under the other memory condition and compare both transcripts side by side. Along the way I see a short, honest explanation of what "Emotional Memory" means conceptually, and a compact card citing SAE's own prior, conservatively-worded experimental result. I understand the core idea within a few minutes without needing to know anything about SAE's internal research process.

## 3. MVP scope

- Serve the two existing frozen synthetic fixtures (`greenhouse`, `new_studio`) as the selectable scenarios.
- Run a scenario segment-by-segment against the existing `NebiusProvider` / `CompatibilityRunner`, under Memory OFF or Memory ON.
- Memory ON loads one already-prepared, operator-supplied artifact through the existing opaque loader (`sae_demo/memory_loader.py`); the artifact itself is not selectable by an anonymous UI user (see Section 13).
- Show the assistant's response after each segment, and let the user advance to the next segment.
- After a run completes, let the user trigger the same scenario under the other memory condition (Demo comparison mode, Section 6) and view both transcripts together.
- Show a small, clearly labeled conceptual Emotional Memory visualization using static/synthetic illustrative content.
- Show the frozen Experiment 8 evidence card (Section 11).
- Show a short disclosure/about panel linking to what this project is and is not.

## 4. Explicit non-goals

M5 does not: implement a Scenario Builder that generates new scenarios from user-supplied ingredients (Section 3's two fixed fixtures are the MVP path — see Section 3's rationale below); implement user accounts, persistence of past runs across sessions, or multi-user shared sessions; implement the Recognition/Activation prototype panel described in `docs/ARCHITECTURE.md` (out of scope for this stage, not requested); support selecting among multiple target models or providers; implement any tooling for producing, editing, or selecting among multiple Emotional Memory artifacts from the UI; or make this specification's existence an implementation instruction — no code is written as part of M5.

On the Scenario Builder question raised by the task: the eventual direction (user-supplied structured ingredients -> AI-generated multi-part scenario -> ordered segments -> inspect/edit upcoming segments -> run) is worth keeping as the long-term shape, but it depends on an AI scenario-generation step that does not exist yet, adds an extra live-model call and a new failure surface (a malformed generated scenario) to a demo whose primary job is reliability in front of judges, and is not needed to demonstrate the core Memory OFF/ON idea. M5's recommendation is to default to the two existing frozen fixtures for the controlled demonstration and treat a generation-based builder as later, optional work, not part of any M5 milestone below.

## 5. Primary user flow

1. Landing screen: one short paragraph explaining what SAE-DEMO is (an existing Emotional Memory export, supplied to an NVIDIA model, compared against the same model with no memory) and what it is not (not the SAE research process, no new experiment).
2. User chooses a scenario (`greenhouse` or `new_studio`).
3. User selects Memory OFF or Memory ON.
4. User starts the scenario run.
5. The current scenario segment is presented.
6. The assistant's response to that segment is shown once it returns.
7. User clicks "Next Segment" to continue; repeat steps 5–6 until the scenario is complete.
8. At completion, the user is offered a "Compare" action that runs the same scenario again under the alternate memory condition and, once that run completes, shows both transcripts together.
9. A compact conceptual Emotional Memory visualization is available (not forced into the main flow) for the user to open.
10. A conservative Experiment 8 evidence card and a disclosure/about panel are available in the same way.

No step requires the user to understand experimental IDs, XNET/XINJ terminology, or any other private vocabulary; none of that vocabulary appears anywhere in the UI.

## 6. Controlled comparison flow (demo comparison mode)

This is the primary hackathon demonstration and the one judges should be steered toward by default. A run in this mode is controlled and replayable: scenario text, segment order, target model, non-reasoning configuration, `max_tokens`, and the behavioral-use policy are held identical to the OFF/ON comparison invariants already frozen in `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md` (Section 7 of that document). The only variable the UI changes between the two runs being compared is Memory OFF vs. Memory ON. Segments in this mode are not editable.

## 7. Interactive exploration flow

A clearly separate mode, visually and textually distinguished from demo comparison mode (a different label and, if screen space allows, a different visual treatment — e.g. a border color or badge reading "Exploration — not a controlled comparison"). In this mode the user may edit the text of upcoming (not-yet-sent) segments before they are sent, using the scenario engine's existing `edit_upcoming_segment` support (`interactive`-mode scenarios only). Any UI copy near this mode must avoid implying that an edited run is a controlled or scientifically valid comparison; it is presented as free exploration of the same mechanism, not as evidence.

## 8. Screen/layout specification

A single-page application with the following areas, described structurally rather than pixel-precisely:

- **Header bar**: project name, one-line description, disclosure/about link.
- **Status strip**: current target model label (static text, e.g. "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B via Nebius"), and a small run-status indicator (idle / running / complete / error).
- **Scenario selector**: a dropdown or two clearly labeled cards for `greenhouse` and `new_studio`.
- **Memory control**: a simple OFF/ON toggle or two-button choice, with the artifact's representation label (e.g. "profile" / "network") shown only when relevant and never exposing artifact internals.
- **Run panel**: scenario progress indicator (e.g. "Segment 3 of 7"), the current segment's text, the assistant's response once returned, and a "Next Segment" button (disabled while a response is pending).
- **Transcript panel**: the completed transcript so far, growing as segments advance.
- **Compare panel**: appears once a run completes; a "Compare with Memory {OFF/ON}" button, and — once that second run completes — both transcripts shown side by side or in a toggle.
- **Conceptual visualization panel**: collapsed/expandable, not shown by default inside the run flow.
- **Experiment 8 evidence card**: collapsed/expandable, same treatment.
- **Disclosure/about panel**: reachable from the header at all times.

## 9. Component specification

Minimum components, each with a single clear responsibility:

- Header / explanation component (static content).
- Model/status indicator component (reads run state only; no polling of provider internals).
- Scenario selector component (lists the two fixtures; no free-text scenario entry in MVP).
- Memory OFF/ON control component (two-state control; disabled once a run has started).
- Scenario progress indicator component (segment index / total).
- Current-segment display component (renders the active segment's text).
- Assistant-response display component (renders the returned response, or a pending/loading state).
- Next-Segment button component (advances the engine by one segment; disabled while pending or when the run is complete).
- Transcript component (renders the full `sent_segments` list from the run trace).
- Compare button / alternate-run component (triggers a second run under the other memory condition using the same scenario; renders both transcripts once both are complete).
- Conceptual memory visualization component (Section 10).
- Experiment 8 evidence card component (Section 11).
- Disclosure/about panel component (links to `docs/DISCLOSURE_BOUNDARY.md`-level information, rendered as user-facing prose, not raw doc links).

## 10. Conceptual visualization specification

Purely conceptual and illustrative. It must not reconstruct, parse, or approximate the real private representation loaded by `memory_loader.py`, and must never resemble live internal model telemetry (no numeric weight bars driven by real data, no live-updating graph tied to the actual payload). Acceptable content: a small static diagram or short animated sequence built from synthetic/example data communicating ideas such as emotional salience, connected experience, persistent weighting, and influence on interpretation — for example, a handful of labeled example nodes with illustrative (not real) connection strengths, clearly captioned "Conceptual illustration — not the actual memory representation." The visualization ships as static assets or hard-coded example data in the frontend; it does not read from `.local/memory/` or any loaded payload at all.

## 11. Experiment 8 evidence presentation

The card uses only this frozen sentence, verbatim, without rewording:

> "A controlled nine-session, three-provider experiment found reproducible condition-associated trajectory differences, including a repeated early curiosity/interest divergence, while several stronger hypotheses remained unresolved."

The card may additionally state, briefly: 3 provider/model families were tested, 3 conditions were compared, 9 sessions were run in total. It must not show raw transcripts, internal experiment IDs, or any other private artifact, and must not claim statistical significance, universal transfer, or a proven mechanism — consistent with Section 9/10 of `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md`.

## 12. Backend/API boundary

Reuses the existing backend building blocks (`ScenarioEngine`, `CompatibilityRunner`, `NebiusProvider`, `memory_loader`) behind a thin API layer. Concepts only — no implementation in this stage:

- **List scenarios** — returns the small fixed set of available scenario identifiers/titles (currently `greenhouse`, `new_studio`).
- **Load scenario** — returns a scenario's segment count, mode, and (for the current segment only) enough detail for the UI to render progress; does not dump every segment's text up front for a frozen-mode run, to preserve the "presented segment by segment" experience.
- **Start run** — begins a new run: scenario id, memory condition (off/profile/network), and comparison-mode flag (demo comparison vs. interactive exploration). Returns a run identifier.
- **Submit/advance segment** — advances the identified run by one segment (interactive mode may optionally carry an edited text payload for the upcoming segment); returns the segment sent and, once available, the model's response.
- **Retrieve run state/transcript** — returns a run's current position, completion status, and transcript so far.
- **Choose memory condition** — implied by "start run"; not a separate mutable operation once a run exists (per the OFF/ON comparison invariants, condition does not change mid-run).
- **Compare completed conditions** — given a completed run, starts (or looks up) the paired run for the alternate memory condition on the same scenario, and returns both transcripts once both are complete.

This surface is intentionally small: one resource ("run"), a handful of operations on it, and no generic CRUD framework, ORM, or database layer implied.

## 13. Memory handling

**Memory ON**: the backend loads the exact prepared artifact via the existing opaque loader (`sae_demo/memory_loader.py`), verifies its envelope and content hash exactly as today, and passes it into `CompatibilityRunner` together with the frozen M4B behavioral-use policy — unchanged from the already-frozen consumption architecture. The backend never parses the artifact's creation structure. **Memory OFF**: the same generic behavioral-use policy is sent, with no memory payload, preserving the OFF/ON comparison invariants.

The specific artifact file used for Memory ON is an operator-side configuration choice (an environment variable or local config pointing at a file under `.local/memory/`), not something an anonymous UI user selects or uploads — this keeps artifact provenance and Hasse's approval of "the specific artifact" (per the frozen IP boundary) entirely on the operator side. The UI needs no knowledge of the artifact's internal structure, only the representation label already used elsewhere (`profile` / `network`) for display purposes.

## 14. API-key/security handling

The Nebius API key is never sent to, stored in, or returned by the frontend in any response or client-visible log. For the hackathon MVP, the key is configured as a backend environment variable (consistent with the existing `.env` / `python-dotenv` pattern already used by `sae_demo/config.py`), read once at backend startup, and never included in any API response body, error message, or backend log line — consistent with `NebiusProvider`'s existing practice of never including raw exception text (which could contain request headers) in error messages. A hosted/shared demo deployment should use the platform's own environment/secret configuration rather than a committed or user-supplied `.env` file. No strong reason has been identified for deviating from backend-side configuration for this MVP (e.g. no per-user key requirement exists for a hackathon demo).

## 15. Runtime/logging boundary

Live run traces, transcripts, and any other runtime output stay under the existing gitignored `.local/` root (`sae_demo/runtime_paths.py`) by default and are never Git-tracked, matching the M3C.1 boundary already in force. Backend logs must not include the API key or any other private configuration value. The prepared Emotional Memory artifact itself is not secret-by-definition — per the frozen IP boundary, Hasse permits sharing the prepared memory artifact itself (subject to his approval of the specific artifact); only the creation/derivation/extraction/freezing/validation method is protected. Logging and documentation for M5 must describe the artifact accordingly and must not describe it as inherently secret.

## 16. Error handling

Minimal, specified states only:

- **Missing API key**: backend fails fast at startup or on first provider call with a clear, generic message; UI shows a simple "demo is not configured" state, no key value ever surfaced.
- **Provider error**: UI shows a generic "the model request failed, try again" state for the affected segment; run state is preserved so the user is not forced to restart.
- **Malformed scenario**: surfaced at scenario-load time via the existing `ValidationReport`/`ScenarioValidationError`; UI shows the scenario as unavailable rather than allowing a broken run to start.
- **Memory integrity failure**: the existing `MemoryPayloadIntegrityError` path (no provider call made) surfaces as a clear "memory verification failed" state; the run does not silently fall back to Memory OFF.
- **Run already completed**: further "advance" calls against a completed run return a clear "run already complete" response rather than erroring ambiguously; the UI simply disables "Next Segment" once complete.
- **Network timeout**: treated the same as a provider error for UI purposes; no automatic silent retry loop.

Nothing beyond these six states is specified; no elaborate retry/backoff framework is introduced at this stage.

## 17. Recommended technical stack

The existing codebase is plain Python: `sae_demo` (dataclasses, no framework), `openai` client, `python-dotenv`, `pytest`, no web framework, no frontend of any kind yet. Recommendation: a lightweight Python web layer (e.g. Flask or FastAPI — either is a small addition on top of the existing `requirements.txt`) exposing the API surface in Section 12, paired with minimal server-rendered or vanilla HTML/CSS/JS on the frontend (no build step, no bundler, no JS framework). This is sufficient for the flow specified above: a handful of screens, simple state (current run, current segment, transcript), and no need for client-side routing complexity, component libraries, or a SPA framework. Adding React, Vue, or similar would introduce a build pipeline and dependency surface with no corresponding benefit for a demo this size, and would not reuse anything already in the project. If, during implementation, a specific interaction (e.g. smooth segment-by-segment reveal) turns out to need more client-side state management than plain JS comfortably handles, a small, dependency-free enhancement (a single vanilla-JS module) is preferred over introducing a framework; that decision is deferred to implementation, not fixed here.

## 18. Mobile/desktop considerations

The primary demo context is a judge or presenter on a laptop; desktop-first layout is the priority. The layout in Section 8 should degrade gracefully to a narrower viewport (single-column stacking of the run panel and transcript) but a dedicated mobile-optimized experience is not required for the hackathon MVP and is not specified further here.

## 19. Acceptance criteria

- A judge with no prior exposure to this project can pick a scenario, choose Memory OFF or Memory ON, and see the scenario run segment by segment within roughly 2–3 minutes, without reading any research documentation.
- The Memory OFF and Memory ON transcripts for the same scenario are viewable together after using the Compare action.
- No private SAE vocabulary, artifact internals, experiment IDs, or the creation/derivation/extraction/freezing/validation method appears anywhere in the UI, API responses, or logs.
- The Experiment 8 evidence card uses only the frozen sentence in Section 11, verbatim.
- The conceptual visualization uses only synthetic/static example data and is clearly labeled conceptual.
- All claims-prohibited language from `docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md` (Section 10 of that document) is absent from all UI copy.
- The API key is never present in any frontend-visible response, error message, or client-side log.

## 20. Proposed implementation milestones

Small and sequential; each is independently demoable.

- **M5A** — minimal web shell + backend health: the chosen lightweight Python web framework wired up, a health/status endpoint, and a static landing page with the header/explanation and disclosure panel. No scenario logic yet.
- **M5B** — scenario run UI: list/select the two fixtures, start a Memory-OFF-only run, present segments one at a time via the existing `ScenarioEngine`, show responses via `NebiusProvider`/`CompatibilityRunner`, "Next Segment" control, transcript panel.
- **M5C** — Memory OFF/ON integration: wire in the opaque memory loader and the frozen M4B policy for a Memory ON run, add the Memory OFF/ON control, preserve the OFF/ON comparison invariants end to end.
- **M5D** — comparison view: the Compare action, running the alternate condition and rendering both transcripts together.
- **M5E** — conceptual visualization + evidence card: the static conceptual memory visualization and the Experiment 8 evidence card, both using only synthetic/static content.
- **M5F** — polish/demo hardening: the error states in Section 16, basic styling toward the calm/technical/modern/human direction in the task, and a final pass checking every acceptance criterion in Section 19.

This decomposition follows directly from the existing architecture (scenario engine and compatibility runner already implemented and tested; only a thin API/UI layer is new) and is not adjusted further from the example shape given in the task.
