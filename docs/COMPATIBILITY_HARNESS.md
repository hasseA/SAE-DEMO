# Compatibility Harness (M3C, Memory OFF only)

## What this is

`sae_demo/compatibility_runner.py` (`CompatibilityRunner`) replays one frozen, synthetic scenario through the live Nebius/NVIDIA provider (`NebiusProvider` from M3A), segment by segment, using the backend scenario engine from M3B. It sends each scenario segment as a user message, keeps prior turns in context, and records the exact user text sent and exact assistant text returned for every turn, along with structural metadata (finish reason, model label, whether the response's `reasoning` field was unexpectedly non-null, completion-token count).

**This is a compatibility check, not a scientific experiment.** It exists to verify that the target model can carry a scripted multi-turn synthetic scenario through this project's provider integration with the confirmed non-reasoning configuration. It draws no scientific conclusions, performs no emotional scoring or interpretation of the responses, and is not a replacement for or a version of SAE's own controlled Experiment 8 methodology.

## Memory OFF only

Every run in this stage sends only the scenario's own segment text — nothing else is added to the conversation context. No Emotional Memory export is loaded, consumed, or referenced anywhere in this component. Memory ON (supplying a bounded Emotional Memory export as additional context) is a separate, later stage and is not implemented here.

## Who runs the live test

This harness makes real API calls and is not exercised by Claude. `scripts/run_compatibility.py` is a human-run CLI: Hasse runs it locally, with his own `NEBIUS_API_KEY` configured in `.env`, to check compatibility against the live Nebius/NVIDIA endpoint. See the README's "Compatibility runner (M3C)" section for usage. Only the offline, fully mocked test suite (`tests/test_compatibility_runner.py`) is run automatically, and it makes no network calls.

## No private SAE content

The system message sent with every run is a short, generic, public-safe sentence (`sae_demo/compatibility_runner.DEFAULT_SYSTEM_MESSAGE`) — it is not derived from, and does not resemble, SAE's private Frame measurement prompt or any other private system prompt. The two fixtures this stage's tests and CLI use (`greenhouse`, `new_studio`) are the entirely synthetic scenarios introduced in M3B; no Experiment 8 material, XNET/XINJ content, or other private SAE data is read, copied, or referenced by this component.
