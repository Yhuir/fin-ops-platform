# Next Prompt

Continue after `planning:read-model-internal-api-contract-harness-design`.

## Current State

- Branch: `dev`
- Authenticated API response-shape smoke is deferred because no non-secret HTTP SLO auth config exists in production env.
- Public unauthenticated page-shell smoke completed against `https://www.yn-sourcing.com`.
- Initial `http://127.0.0.1:18001` page-shell probe was classified as wrong-base operator evidence because the API listener returned 17/17 404 for `/fin-ops/*`.
- Public base rerun passed:
  - `probe_count=17`
  - `failed_probe_count=0`
  - all default `/fin-ops/*` page-shell paths returned 200
  - `max_p95_ms=27.782`
- `/health/ready` remained ready before and after.
- Row254 selected a T0-owned read-only shadow-read rehearsal runbook as the next evidence boundary.
- Row255 executed the rehearsal runbook and classified it as `production-evidence-deferred`:
  - direct shell lacked DB config;
  - runtime env execution returned `gate_recommendation=BLOCKED`;
  - `local_pickle` is not a comparable primary for current production PostgreSQL runtime;
  - `workbench_read_models` hit a PostgreSQL statement timeout;
  - output was redacted/hash based and `/health/ready` stayed ready.
- Row256 selected a PostgreSQL-native Workbench high-row query-plan/read-only runbook as the next boundary because Row255's concrete PostgreSQL-side gap was `workbench_read_models` statement timeout.
- Row257 collected read-only PostgreSQL Workbench high-row evidence:
  - active generation metadata rows: 3491;
  - largest active scope: 1624 rows;
  - physical historical tables remain large: `workbench_rows=654911`, `workbench_group_rows=729629`;
  - representative active page-like queries use generation/scope indexes and corrected EXPLAIN completed;
  - no payload rows or mutations were used.
- Row258 selected unauthenticated API status/shape classification with existing `http_slo_probe` as the next safe evidence boundary. This will not prove authenticated API closure.
- Row259 ran API-only unauthenticated classification:
  - 38/38 default API probes returned 401;
  - public API surfaces are consistently auth-gated;
  - no response body or payload row was stored;
  - `/health/ready` stayed ready.
- Row260 reconciled Row259 and selected an internal API contract harness design:
  - authenticated production HTTP retry is still premature because no non-secret HTTP SLO auth config exists;
  - public browser data smoke is still premature because API data routes are auth-gated;
  - another unauthenticated route sweep would not add response-shape evidence;
  - CodeGraph confirmed this backend is not Flask and existing local tests use `Application.handle_request(...)` / route-owner seams.
- Row261 designed the internal API contract harness:
  - use `Application.handle_request(...)`, not Flask or production HTTP;
  - use existing unittest default auth for local success-shape evidence plus explicit negative auth guard checks;
  - seed representative route inventory from `http_slo_probe.DEFAULT_API_PROBES`;
  - assert sanitized envelopes, status codes, freshness/readiness metadata and permission denial shapes without full payload snapshots.
- Authenticated API, browser hydration/data, high-row and module-specific closure audits remain open.
- No global or module closure is claimed.

## Next Boundary

`contract:read-model-internal-api-contract-harness-implementation`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Read:
   - `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
   - `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
   - this prompt
4. Read `analysis/production-read-model-public-page-shell-smoke-runbook-2026-06-25.md`.
5. Read `analysis/planning-post-public-page-shell-smoke-next-boundary-selection-2026-06-25.md`.
6. Read `analysis/production-read-model-shadow-read-rehearsal-read-only-runbook-2026-06-25.md`.
7. Read `analysis/planning-post-shadow-read-rehearsal-next-boundary-selection-2026-06-25.md`.
8. Read `analysis/planning-post-workbench-high-row-query-plan-next-boundary-selection-2026-06-25.md`.
9. Read `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`.
10. Read `analysis/planning-post-unauthenticated-api-classification-next-boundary-selection-2026-06-25.md`.
11. Read `analysis/planning-read-model-internal-api-contract-harness-design-2026-06-25.md`.
12. Implement the smallest local GET-only API contract harness test for representative read-model-heavy endpoints, using existing fixtures/stubs and sanitized response-shape assertions.
13. Use CodeGraph before any implementation-oriented decision about `Application`, auth/session helpers or route-owner classes.

## Stop Gates

- Do not print/store secrets, DSNs, tokens, cookies, env values or sensitive payload rows.
- Do not run production mutation, deploy, restart, requeue, repair, replay workers or mutate DB/queue/readiness state.
- Do not implement a production auth bypass or print/store cookies, tokens, DSNs, env values or secrets.
- Do not introduce a Flask test client; this backend uses `Application` plus `ThreadingHTTPServer` / `BaseHTTPRequestHandler`.
- Do not add broad payload snapshots or fixture data just to force every route through one harness.
- Do not claim module/global closure from public page-shell smoke.
