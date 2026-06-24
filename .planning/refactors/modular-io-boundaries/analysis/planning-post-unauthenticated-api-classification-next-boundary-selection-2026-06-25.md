# Post Unauthenticated API Classification Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-unauthenticated-api-classification-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:read-model-internal-api-contract-harness-design`

## Goal

Reconcile Row259 unauthenticated API status/shape evidence and choose the next safe path for API/browser closure evidence.

This slice does not claim authenticated API, browser, module or global closure.

## Inputs Reviewed

- `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-public-page-shell-smoke-runbook-2026-06-25.md`
- `analysis/planning-post-public-page-shell-smoke-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-shadow-read-rehearsal-read-only-runbook-2026-06-25.md`
- `analysis/planning-post-shadow-read-rehearsal-next-boundary-selection-2026-06-25.md`
- `analysis/production-workbench-read-model-high-row-query-plan-read-only-runbook-2026-06-25.md`
- `analysis/planning-post-workbench-high-row-query-plan-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`
- CodeGraph context for `Application`, route-owner classes, HTTP dispatch and existing `Application.handle_request(...)` tests.
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

## Reconciled Row259 Evidence

Row259 proved:

- `/health/ready` stayed ready before and after the API-only classification.
- `http_slo_probe --allow-unauthenticated --no-default-page-probe` exercised the default 38 API probes without credentials.
- All 38 API probes returned `401`.
- No response bodies, payload rows, tokens, cookies, DSNs, env values or secrets were stored.
- No deploy, restart, requeue, repair, replay, DB write, queue/readiness mutation or `--apply` occurred.

Row259 did not prove:

- authenticated API response shapes;
- browser hydration or page data behavior;
- permission-specific success/denial behavior beyond unauthenticated 401;
- read-model status/cache status metadata for any API route;
- operation-barrier behavior;
- module or global closure.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Final closure audit | Rejected | Authenticated API, browser hydration/data, operation-barrier and module-specific evidence remain open. |
| Retry authenticated production HTTP smoke | Rejected | Row252 already proved no non-secret `FIN_OPS_HTTP_SLO_BEARER_TOKEN`, `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE` is configured. Retrying would reproduce `auth_missing` unless runtime configuration changes. |
| Browser data smoke against the public site | Rejected for now | Public page shell already passed, but API data routes are auth-gated. Browser data smoke would mostly re-prove unauthenticated denial or shell availability. |
| Ask for or print auth cookies/tokens | Forbidden | Goal rules forbid asking for or storing private secrets, cookies or tokens. |
| Production non-secret auth provisioning implementation | Deferred | A deployed non-secret test actor/session path would change runtime security posture and needs a clearer auth/session contract before implementation. |
| Another production read-only HTTP route sweep | Rejected | Existing public HTTP routes now have page shell 200 and API 401 classification; another unauthenticated sweep would not produce read-model response-shape evidence. |
| Internal API contract harness design | Accepted | CodeGraph shows this backend is not Flask; it uses `Application`, `BaseHTTPRequestHandler` dispatch, route-owner classes and existing tests that instantiate `Application` and call `handle_request(...)`. A planning/design slice can define how to reuse those local seams to assert API response envelopes without production secrets or mutation. |

## Selected Boundary

Select `planning:read-model-internal-api-contract-harness-design`.

The next boundary must design, but not yet implement broadly, a local/internal read-model API contract harness that can answer:

1. Which read-model-heavy endpoints can be exercised through existing `Application.handle_request(...)`, route-owner classes or narrowly scoped test fixtures.
2. How auth/session requirements should be satisfied without production cookies, tokens, DSNs or secret env values.
3. Which response fields may be asserted as contract evidence without selecting or storing full payload rows.
4. Which endpoints remain unsuitable for harness evidence because they require real PostgreSQL, worker convergence, browser hydration or sensitive production data.
5. Which single follow-up implementation slice is smallest and safest if the design is accepted.

## Harness Design Guardrails For Row261

- Treat the harness as local/contract evidence, not production closure.
- Prefer existing `Application.handle_request(...)` tests, route-owner classes, builders, fake/stub stores and fixtures.
- Do not introduce a Flask test client; this backend is served by `ThreadingHTTPServer` / `BaseHTTPRequestHandler`.
- Do not bypass permission semantics silently. Any test-auth or local-session mechanism must be explicit, existing, and documented.
- Do not add broad fixture data or payload snapshots.
- Assert envelopes and metadata such as status code, `error`, `message`, `rows`/count presence, `read_model_status`, `cache_status`, `refresh_enqueued`, `freshness_targets`, `read_model_scope_keys`, operation-barrier fields and empty/error states where the endpoint contract exposes them.
- Keep browser smoke separate unless the design proves a non-secret page data path.
- Do not run production commands, deploys, restarts, requeues, repairs, worker replays, DB writes or `--apply`.

## State-Machine Impact

- Row259 remains `production-evidence-deferred`.
- Row260 closes as `planning-closed`.
- Row261 is inserted as `pending`.
- No module closure changes to `closed`.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term architecture docs change in this planning slice because no API behavior, business rule, worker, read model, permission or state-machine contract changed.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: applicable to Row261 design and likely follow-up implementation; this slice selects the harness design path.
4. Read model/cache/background job tests: applicable to future harness assertions for `read_model_status`, `cache_status`, freshness and enqueue metadata.
5. Frontend component and interaction tests: still open; browser data smoke remains deferred until non-secret auth/harness evidence exists.
6. End-to-end business-flow integration tests: still open; this planning slice does not cross module behavior.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command is executed in this planning slice.
