# SAE-DEMO Demo / Release Readiness Checklist (M5G)

This is an **operational** checklist for a human to walk through before a release/disclosure review or a hackathon submission. It is not a scientific document, and checking every box here does not by itself authorize publication, deployment, or submission — those remain separate, explicit decisions (see "Release boundary" at the end).

Distinguish two different things while working through this list, per the corrected disclosure boundary this stage confirmed:

- **The Emotional Memory artifact itself** (its existence, and its use as opaque context in a Memory ON run) is not something this checklist treats as forbidden to demonstrate.
- **The private method** that creates one — extraction/derivation machinery, structuring/weighting logic, freezing/construction methodology, the private XNET/XINJ schema or implementation, recognition/activation algorithms, model-adaptation/alignment technique — must never appear in this repository or be explained by anyone working in it, regardless of whether a prepared artifact is being demonstrated.

## Repository hygiene

- [ ] `git status` is clean (no uncommitted changes, nothing untracked that should be tracked or ignored)
- [ ] `scripts/check_disclosure_boundary.py` passes (all checks report `[PASS]`)
- [ ] `.env` is gitignored and not tracked
- [ ] `.local/` is gitignored and not tracked
- [ ] A staged-diff secret scan (API keys, tokens, credentials) is clean
- [ ] No private SAE source, path, or schema/implementation detail (see distinction above) is present in any tracked file

## Local configuration

- [ ] A Nebius API key is configured locally (`NEBIUS_API_KEY`, via `.env` or the environment) — not committed
- [ ] A prepared Emotional Memory artifact is configured locally if Memory ON is to be demonstrated (`SAE_DEMO_MEMORY_FILE`) — not committed

## Functional smoke checks

- [ ] `/api/health` and `/api/status` respond correctly with the server running locally
- [ ] A built-in scenario Memory OFF run completes end to end
- [ ] A built-in scenario Memory ON run completes end to end (with a configured artifact)
- [ ] The alternate-condition comparison completes and renders side by side
- [ ] The Scenario Wizard's ingredient form and prompt generation work (Steps 1–2)
- [ ] A pasted seven-section story parses and can be reviewed/edited (Steps 3–4)
- [ ] A custom scenario freezes successfully and becomes runnable (Step 5)
- [ ] A frozen custom scenario's comparison completes and renders (Step 6)

## Content and presentation

- [ ] No memory-creation-*method*, private schema, or private research-identifier detail is visible anywhere in the UI or an API response (the configured artifact's use as context in a Memory ON run is expected and is not a violation of this item)
- [ ] The conceptual Emotional Memory visualization's "illustrative model only" disclaimer is visible and unchanged
- [ ] The Experiment 8 evidence card's approved sentence is exact, unmodified, and not strengthened
- [ ] A narrow/mobile-width smoke check has been done (layout doesn't break, nothing overflows unreadably)

## Shutdown and process hygiene

- [ ] The local server stops cleanly (no lingering process on its port)
- [ ] No secret (API key, credential, token) is present anywhere in the repository

## Release boundary

- [ ] A release/disclosure review has been completed by a human before anything below is authorized
- [ ] No Git remote has been configured and nothing has been pushed, unless a human has explicitly authorized it
- [ ] No public repository, deployment, or Devpost (or similar) submission has been performed, unless a human has explicitly authorized it

This checklist itself does not authorize any of the items in "Release boundary" — each requires its own explicit, separate approval.
