# Local API Key and Provider Usage Safety

SAE-DEMO is distributed as a locally runnable project. Each user supplies
their own Nebius API key to their own FastAPI process through a local `.env`
file. Provider usage and any provider-side rate or spending limits therefore
belong to that user's Nebius account; SAE-DEMO does not impose an artificial
inference-call ceiling.

## Provider-triggering route

`POST /api/runs` prepares a run but does not request inference. The Nebius
Token Factory request occurs only when a valid, active run calls:

- `POST /api/runs/{run_id}/advance`

Each such call advances one scenario segment and attempts one provider
request. Memory OFF and Memory ON use the same route, model configuration,
completion-token budget, behavioral policy, history construction, and provider
adapter. Only the presence of the configured memory payload differs.

The scenario wizard, custom-scenario preparation, health, status, scenario
listing, run creation, alternate-run creation, run-state, and comparison routes
do not call the provider.

## Key handling

- `NEBIUS_API_KEY` is read only from the local server process environment.
- `.env` is gitignored and excluded from the Docker build context.
- The key is never embedded in frontend assets or returned by API responses.
- `/api/status` exposes only the safe `provider_configured` boolean.
- Missing provider configuration and provider failures use generic errors.

Users should monitor usage and configure any desired budgets, alerts, or
limits in their own Nebius account. If someone independently hosts SAE-DEMO as
a shared public service, that operator—not this local release—must add suitable
platform access controls, edge rate limiting, durable quotas, and provider-side
budget controls for their threat model.
