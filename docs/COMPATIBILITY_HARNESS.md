# Compatibility Harness (M3C, extended in M3D with an opaque memory path, M4A with a behavioral-use policy, M4B with a scenario-grounding rule)

## What this is

`sae_demo/compatibility_runner.py` (`CompatibilityRunner`) replays one frozen, synthetic scenario through the live Nebius/NVIDIA provider (`NebiusProvider` from M3A), segment by segment, using the backend scenario engine from M3B. It sends each scenario segment as a user message, keeps prior turns in context, and records the exact user text sent and exact assistant text returned for every turn, along with structural metadata (finish reason, model label, whether the response's `reasoning` field was unexpectedly non-null, completion-token count).

**This is a compatibility check, not a scientific experiment.** It exists to verify that the target model can carry a scripted multi-turn synthetic scenario through this project's provider integration with the confirmed non-reasoning configuration. It draws no scientific conclusions, performs no emotional scoring or interpretation of the responses, and is not a replacement for or a version of SAE's own controlled Experiment 8 methodology.

## Memory OFF by default; an opaque Memory ON path exists (M3D)

By default, every run sends only the scenario's own segment text — nothing else is added to the conversation context. This is unchanged from M3C.

As of M3D, `CompatibilityRunner` can optionally be given an already-loaded, opaque memory-payload string (see `sae_demo/memory_loader.py`) to inject as one isolated, untouched message ahead of the scenario. The runner never loads, parses, or interprets that payload — it only places the exact string it is given into the conversation. `scripts/run_compatibility.py` exposes this as `--memory {off,profile,network}` plus `--memory-file PATH`; no artifact name, path, or content is hardcoded anywhere in tracked source.

**No live Memory ON run has been executed as part of this or any prior stage.** This is implementation and offline-tested wiring only. A live compatibility check with memory attached is a deliberate, separate, human-run action, and remains scoped exactly as narrowly as the Memory OFF live check described below.

## Emotional Memory vs. behavioral-use policy (M4A)

**These are two separate things, and this project keeps them separate on purpose.**

Emotional Memory is the prepared artifact itself — the existing, unchanged, opaque working representation loaded from `.local/memory/` via `sae_demo/memory_loader.py`. Neither M4A nor M4B rewrite, summarize, sanitize, or otherwise transform it in any way; the exact payload string a caller loaded is the exact string this project sends, verified byte-for-byte (see "Payload integrity" below). It is not "just a prompt" — this project has no opinion on, and no need to know, what it structurally is; it is treated as an opaque input, exactly as before M4A.

The behavioral-use policy is different: it is one short, generic, independently-written instruction this project's *consumer* sends about how *any* supplied background context — memory or otherwise — should be used in a response. It says nothing about what the context is, how it was produced, or what it contains. It is public-safe consumption policy authored entirely within SAE-DEMO, not a rendering, rewording, or approximation of anything from the private SAE repository. **This is a consumption-layer behavior rule. It does not modify Emotional Memory.** See `sae_demo/compatibility_runner.DEFAULT_BEHAVIORAL_USE_POLICY` for its exact text.

**Comparison symmetry.** The behavioral-use policy is off by default at the `CompatibilityRunner` level (so it never changes any pre-M4A test's behavior), but `scripts/run_compatibility.py` sends it unconditionally and identically for `--memory off` and for `--memory profile`/`network` alike — it is never a condition-specific difference between a Memory OFF and a Memory ON run. Only the presence of the memory payload itself differs between conditions.

**Context placement.** Both the behavioral-use policy and, when present, the memory context label and the opaque payload are each their own isolated `system`-role message, sent once, ahead of the scenario. `system` is the strongest context-isolation role the current Nebius adapter passes through; this project does not invent or rely on any other role. M4B did not change this placement.

**Payload integrity.** `scripts/run_compatibility.py` passes the memory artifact's already-verified `content_sha256` (from `sae_demo/memory_loader.py`'s own load-time check) through to `CompatibilityRunner`, which independently re-hashes the exact string it is about to place into the conversation and refuses to send it — making no provider call for that turn — if the hash no longer matches. This is a hash comparison only; the runner never parses the payload to perform it.

## Scenario-grounding rule (M4B)

M3D's private compatibility testing showed that, even after M4A's anti-recitation rule reduced explicit representation recitation (numeric weights, "emotional map" language, representation-like tables), the model could still introduce concrete narrative details — people, places, events, objects, remembered scenes — that trace to background context rather than to anything actually present in the current conversation.

The intended boundary, preserved by M4B: **background context may influence behavior and interpretation** — tone, salience, emotional or relational stance, which current-scenario details feel important — **but concrete narrative facts in the assistant's response should remain grounded in the active user conversation**, unless the user explicitly asks the assistant to discuss the background context directly. In short: state may transfer; the source story should not be invented into the current story.

M4B extends `DEFAULT_BEHAVIORAL_USE_POLICY`'s *text only* — no new constructor parameter, no context-placement change, no change to memory handling. The existing M4A anti-recitation sentences remain present verbatim; one additional, generic sentence is appended stating the grounding constraint. **This is a consumption-layer behavior rule. It does not modify Emotional Memory** — the payload itself, and its SHA-256, are unchanged by this stage.

This rule constrains *invented concrete detail*, not emotional engagement: the policy explicitly states that background context may still shape interpretation, tone, and emotional or relational stance. Whether the model actually follows this instruction is a live-model question, out of scope for this stage's offline tests — see "Who runs the live test" below.

## Who runs the live test

This harness makes real API calls and is not exercised by Claude. `scripts/run_compatibility.py` is a human-run CLI: Hasse runs it locally, with his own `NEBIUS_API_KEY` configured in `.env`, to check compatibility against the live Nebius/NVIDIA endpoint. See the README's compatibility-runner sections for usage. Only the offline, fully mocked test suite (`tests/test_compatibility_runner.py`, `tests/test_memory_loader.py`) is run automatically, and it makes no network calls. Whether the target model actually honors the anti-recitation and scenario-grounding rules is not something a mocked-provider test can demonstrate; that requires a live run, deliberately deferred to a later, separate stage.

## No private SAE content in tracked source

The system message sent with every run is a short, generic, public-safe sentence (`sae_demo/compatibility_runner.DEFAULT_SYSTEM_MESSAGE`) — it is not derived from, and does not resemble, SAE's private Frame measurement prompt or any other private system prompt. The short label placed ahead of an injected memory payload (`DEFAULT_MEMORY_CONTEXT_LABEL`) and the behavioral-use policy (`DEFAULT_BEHAVIORAL_USE_POLICY`) are likewise independently written and generic, and are not modeled on SAE's private XINJ framing text or any private structural vocabulary. The two fixtures this stage's tests and CLI use (`greenhouse`, `new_studio`) are the entirely synthetic scenarios introduced in M3B; no Experiment 8 material, XNET/XINJ content, or other private SAE data is read, copied, or referenced by any tracked file in this repository.

A memory payload, when one is supplied at runtime via `--memory-file`, comes only from a local, gitignored file under `.local/memory/` (see `docs/RUNTIME_DATA_BOUNDARY.md`) that the operator points at explicitly — it is never read from, written to, or embedded in tracked source, and this repository's tests use only synthetic fake payload strings, never any real artifact content.
