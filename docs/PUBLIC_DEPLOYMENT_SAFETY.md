# Public Deployment Safety

This document covers the public web surface and provider-cost boundary of
SAE-DEMO. It is deployment guidance only; it does not indicate that the app has
been deployed.

## Provider-triggering routes

`POST /api/runs` prepares a run and requires valid server-side provider
configuration, but it does not itself request inference. The actual paid Nebius
Token Factory inference request occurs when a client calls:

- `POST /api/runs/{run_id}/advance`

Each successful call advances one scenario segment and makes one provider
request. `POST /api/runs/{run_id}/alternate` prepares a fresh opposite-mode
run, but its provider requests likewise occur only through that run's
`/advance` endpoint.

The scenario-wizard, custom-scenario, health, status, scenario-listing, run
state, and comparison routes do not call the provider.

## Application safeguards

- The Nebius API key is read only from the server process environment. It is
  never returned to the frontend, API responses, or logs by the application.
- A run cannot be created without provider configuration, and provider errors
  are returned as generic messages.
- Each run has a fixed number of scenario segments, rejects advancement after
  completion or failure, and uses a bounded per-turn completion-token setting
  (`SAE_DEMO_MAX_TOKENS`, default `400`).
- Run and comparison state is process-local and is cleared on restart.
- Every inference attempt passes through one shared, thread-safe reservation
  point immediately before the provider call, identically for Memory OFF and
  Memory ON. Provider failures consume their reserved slot.
- `SAE_DEMO_MAX_INFERENCE_CALLS_PER_CLIENT` limits one server-issued browser
  session (default `20`) and `SAE_DEMO_MAX_INFERENCE_CALLS_TOTAL` limits the
  whole process (default `200`). Both ceilings are always active.

These are deliberately minimal hackathon-demo controls, not production
authentication, authorization, or a durable/distributed spending system.
The public demo intentionally has no password or login, so judges can use it
directly.
Session identities and counters are process-local, reset on restart, and are
not coordinated across workers or replicas. A client can clear its cookie or
use multiple clients to evade the per-client ceiling; the per-process total
still applies until restart.

## Minimum protection before public deployment

For the bounded hackathon demo, choose conservative per-client and total
ceilings for the expected judging traffic. Also use an edge/proxy rate limit
and Nebius-side budget or usage alerts where available.
Keep `NEBIUS_API_KEY` exclusively in server-side runtime secret configuration;
never put it in an image, Docker build argument, repository file, browser code,
or client request.

Prefer a single application worker if relying on the total ceiling, and treat
restarts as resetting the budget. For an unrestricted anonymous service, use
durable centralized quotas, identity-aware authentication where appropriate,
edge controls, and provider-side hard limits; the process-local safeguards here
are not sufficient for that threat model.
