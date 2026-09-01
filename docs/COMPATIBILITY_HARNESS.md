# Compatibility Harness (M3C, extended in M3D with an opaque memory path)

## What this is

`sae_demo/compatibility_runner.py` (`CompatibilityRunner`) replays one frozen, synthetic scenario through the live Nebius/NVIDIA provider (`NebiusProvider` from M3A), segment by segment, using the backend scenario engine from M3B. It sends each scenario segment as a user message, keeps prior turns in context, and records the exact user text sent and exact assistant text returned for every turn, along with structural metadata (finish reason, model label, whether the response's `reasoning` field was unexpectedly non-null, completion-token count).

**This is a compatibility check, not a scientific experiment.** It exists to verify that the target model can carry a scripted multi-turn synthetic scenario through this project's provider integration with the confirmed non-reasoning configuration. It draws no scientific conclusions, performs no emotional scoring or interpretation of the responses, and is not a replacement for or a version of SAE's own controlled Experiment 8 methodology.

## Memory OFF by default; an opaque Memory ON path exists (M3D)

By default, every run sends only the scenario's own segment text — nothing else is added to the conversation context. This is unchanged from M3C.

As of M3D, `CompatibilityRunner` can optionally be given an already-loaded, opaque memory-payload string (see `sae_demo/memory_loader.py`) to inject as one isolated, untouched message ahead of the scenario. The runner never loads, parses, or interprets that payload — it only places the exact string it is given into the conversation. `scripts/run_compatibility.py` exposes this as `--memory {off,profile,network}` plus `--memory-file PATH`; no artifact name, path, or content is hardcoded anywhere in tracked source.

**No live Memory ON run has been executed as part of this or any prior stage.** This is implementation and offline-tested wiring only. A live compatibility check with memory attached is a deliberate, separate, human-run action, and remains scoped exactly as narrowly as the Memory OFF live check described below.

## Who runs the live test

This harness makes real API calls and is not exercised by Claude. `scripts/run_compatibility.py` is a human-run CLI: Hasse runs it locally, with his own `NEBIUS_API_KEY` configured in `.env`, to check compatibility against the live Nebius/NVIDIA endpoint. See the README's compatibility-runner sections for usage. Only the offline, fully mocked test suite (`tests/test_compatibility_runner.py`, `tests/test_memory_loader.py`) is run automatically, and it makes no network calls.

## No private SAE content in tracked source

The system message sent with every run is a short, generic, public-safe sentence (`sae_demo/compatibility_runner.DEFAULT_SYSTEM_MESSAGE`) — it is not derived from, and does not resemble, SAE's private Frame measurement prompt or any other private system prompt. The short label placed ahead of an injected memory payload (`DEFAULT_MEMORY_CONTEXT_LABEL`) is likewise independently written and generic, and is not modeled on SAE's private XINJ framing text. The two fixtures this stage's tests and CLI use (`greenhouse`, `new_studio`) are the entirely synthetic scenarios introduced in M3B; no Experiment 8 material, XNET/XINJ content, or other private SAE data is read, copied, or referenced by any tracked file in this repository.

A memory payload, when one is supplied at runtime via `--memory-file`, comes only from a local, gitignored file under `.local/memory/` (see `docs/RUNTIME_DATA_BOUNDARY.md`) that the operator points at explicitly — it is never read from, written to, or embedded in tracked source, and this repository's tests use only synthetic fake payload strings, never any real artifact content.
