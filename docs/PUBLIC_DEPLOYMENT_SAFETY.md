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

## Existing protections

- The Nebius API key is read only from the server process environment. It is
  never returned to the frontend, API responses, or logs by the application.
- A run cannot be created without provider configuration, and provider errors
  are returned as generic messages.
- Each run has a fixed number of scenario segments, rejects advancement after
  completion or failure, and uses a bounded per-turn completion-token setting
  (`SAE_DEMO_MAX_TOKENS`, default `400`).
- Run and comparison state is process-local and is cleared on restart.

These are correctness and secret-handling protections, not abuse controls.
There is currently no authentication, authorization, per-client rate limit,
request quota, or spending cap in SAE-DEMO. Anyone who can reach the app can
create runs and call the inference-triggering endpoint repeatedly. In-memory
run limits do not prevent repeated new runs or distributed traffic.

## Minimum protection before public deployment

For the bounded hackathon demo, place the entire application behind a
deployment-platform access gate (for example, HTTP Basic Auth or an equivalent
judge credential) and an edge/proxy rate limit. Set Nebius-side budget or usage
alerts where the account supports them. Keep `NEBIUS_API_KEY` exclusively in
the deployment platform's server-side secret configuration; never put it in an
image, Docker build argument, repository file, browser code, or client request.

If the hosting platform can enforce both the access gate and rate limit before
traffic reaches SAE-DEMO, no application-code change is required for a
credentialed hackathon deployment. If the app must be reachable as an
unrestricted anonymous public inference service, abuse protection does require
code or an external gateway before deployment. Do not expose the current
provider-triggering route anonymously without such protection.
