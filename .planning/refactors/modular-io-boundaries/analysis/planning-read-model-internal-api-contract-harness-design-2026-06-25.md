# Read Model Internal API Contract Harness Design - 2026-06-25

**Boundary:** `planning:read-model-internal-api-contract-harness-design`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `contract:read-model-internal-api-contract-harness-implementation`

## Goal

Design the smallest local/internal API contract harness path that can advance read-model response-shape evidence after production HTTP API smoke was blocked by missing non-secret auth config and public unauthenticated API probes returned 401.

This design does not implement the harness, run production commands, change runtime auth, or claim authenticated API/browser/module/global closure.

## Inputs Reviewed

- `analysis/planning-post-unauthenticated-api-classification-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-unauthenticated-api-status-shape-classification-runbook-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
- `docs/modules/README.md`
- `docs/dev/index.md`
- `docs/app-architecture/README.md`
- CodeGraph context for:
  - `Application.handle_request(...)`;
  - `_handle_request_untracked(...)`;
  - `_enforce_route_access(...)`;
  - route-owner classes;
  - existing `Application.handle_request(...)` API tests.
- `backend/src/fin_ops_platform/app/auth.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `tests/test_auth_guard.py`
- Representative existing route tests:
  - `tests/test_pending_invoice_api.py`
  - `tests/test_input_invoice_usage_api.py`
  - `tests/test_output_invoice_collection_api.py`
  - `tests/test_workbench_v2_api.py` via CodeGraph context

## Current Facts

- Production has no configured non-secret `FIN_OPS_HTTP_SLO_BEARER_TOKEN`, `FIN_OPS_HTTP_SLO_ADMIN_TOKEN` or `FIN_OPS_HTTP_SLO_COOKIE`; authenticated production HTTP smoke is deferred.
- Public API-only `http_slo_probe --allow-unauthenticated` returned 401 for all 38 default API probes; unauthenticated probing cannot provide read-model response-shape evidence.
- Public page-shell smoke already proves shell availability for 17 `/fin-ops/*` paths but not browser data hydration.
- The backend is not Flask. It is an `Application` served by `ThreadingHTTPServer` / `BaseHTTPRequestHandler`.
- `Application.handle_request(method, path, body, headers)` is already used heavily in tests and returns the project `Response` object.
- `handle_request(...)` routes through `_enforce_route_access(...)` before API dispatch, so a local harness can exercise auth behavior without starting an HTTP server.
- In unittest contexts, default test auth is enabled unless `FIN_OPS_TEST_DEFAULT_AUTH=0`; `tests/test_auth_guard.py` proves missing token returns 401 when default test auth is disabled.
- Existing API tests already install narrow fake/stub services or repositories and assert response shape for read-model-heavy routes.
- `http_slo_probe.DEFAULT_API_PROBES` is a useful route inventory for representative API smoke, but production probe output stores only metadata and does not define full response contracts.

## Design Decision

Build the next implementation slice as a local contract harness around `Application.handle_request(...)`, not around production HTTP and not around a new Flask/test-client abstraction.

The harness should reuse the existing `http_slo_probe.DEFAULT_API_PROBES` names and paths as the first matrix seed, then classify each probe into one of these local evidence categories:

| Category | Meaning | Row262 expected handling |
| --- | --- | --- |
| `contract-shape-local` | Endpoint can be exercised against `Application.handle_request(...)` with default test auth and local fixture/stub data. | Assert status and sanitized envelope keys/counts. |
| `auth-guard-local` | Endpoint proves auth/permission behavior rather than success shape. | Assert 401/403/error envelope using `FIN_OPS_TEST_DEFAULT_AUTH=0` or stubbed identity. |
| `deferred-production-data` | Endpoint requires real PostgreSQL/high-row/worker convergence to prove meaningful data behavior. | Record deferral; do not fabricate payload evidence. |
| `deferred-browser` | Endpoint or page behavior requires browser hydration/client interaction. | Keep for a future Playwright/browser slice. |
| `not-read-model-closure` | Endpoint is health/session/settings/supporting status rather than read-model closure evidence. | Assert only if needed to protect auth/session/dashboard envelope. |

## Harness Scope

Row262 should start with a focused GET-only matrix, using `DEFAULT_API_PROBES` as route inventory and explicit per-probe expectations.

Recommended first implementation coverage:

| Area | Probe examples | Local shape assertions |
| --- | --- | --- |
| Auth/session guard | `/api/session/me`, protected read route without default test auth | 401/403 envelopes stay explicit; default test auth is documented as local-only. |
| Workbench read models | `/api/workbench/summary`, `/api/workbench/groups`, `/api/workbench/settings` | status code is 200 or 202; payload exposes summary/groups/settings envelope or explicit refreshing/error envelope. |
| Pending invoices | rows, filter-options, rules | direction/filter/pagination/rows or fields/rules envelopes; no raw row snapshot. |
| Input invoice usage | rows, filter-options, payment-status-rules | pagination/rows, fields, rules envelopes and detail route smoke where existing fixtures are cheap. |
| Output invoice collections | rows, filter-options, status-rules | pagination/rows, fields, rules envelopes and detail route smoke where existing fixtures are cheap. |
| Cost/tax/read-model summaries | tax offset rows/summary, cost statistics summary/explorer | summary/items/rows/error/refreshing envelopes without asserting sensitive values. |
| Search/no-OA/bank/batch/turnover | representative list/search/tag selection routes | status plus top-level envelope keys/counts; defer high-row or real-data claims. |

Row262 does not need to fully cover all 38 probes in one code change if fixture setup becomes broad. If a probe needs expensive domain construction, the implementation should record it as `deferred-production-data` or `deferred-follow-up-fixture` rather than adding large speculative fixtures.

## Auth And Permission Rules

- Do not add any production auth bypass.
- Do not set or print real cookies, tokens, DSNs or env secret values.
- Use existing unittest default test auth as the local success-session seam.
- Add/keep explicit negative auth checks that disable default test auth and assert protected routes return `401` with `invalid_oa_session`.
- For permission-sensitive mutations or admin routes, prefer existing `tests/test_auth_guard.py` patterns with stubbed `OAUserIdentity`.
- Do not call route-owner methods directly for endpoints whose contract includes auth, route normalization or HTTP response mapping. Direct route-owner calls can supplement but not replace `Application.handle_request(...)` contract evidence.

## Output And Data Minimization Rules

- Assert presence/type/count-level fields, not full payload rows.
- Do not create golden snapshots with business-sensitive rows.
- Do not print payload bodies in controller docs.
- Allowed assertion examples:
  - `status_code in {200, 202}`;
  - top-level `error` / `message` for denied or unavailable states;
  - `rows` is a list and `pagination`/`summary` keys exist;
  - `fields` or `rules` list exists;
  - `read_model_status`, `cache_status`, `refresh_enqueued`, `freshness_targets`, `read_model_scope_keys` where the endpoint exposes them;
  - refreshing envelopes have explicit status and do not pretend stale data is fresh.

## Proposed Row262 Files

Preferred implementation shape:

- Add a targeted test file such as `tests/test_read_model_api_contract_harness.py`.
- Optionally add a small test-only helper inside the test file for:
  - building `Application` in a temporary data directory;
  - invoking `handle_request(...)`;
  - parsing JSON bodies;
  - asserting sanitized envelope contracts;
  - disabling default test auth for negative checks.

Avoid adding production code unless the first implementation proves a reusable non-test tool is necessary. If a reusable helper is needed later, it should live under an existing tools/testing boundary and must not change runtime auth behavior.

## Stop Gates For Row262

- Harness requires production secrets, cookies, tokens, DSNs or env secret values.
- Harness requires production HTTP, browser login, deploy, restart, queue mutation, DB mutation, worker replay, repair or `--apply`.
- Fixture setup becomes broad enough to duplicate domain tests or invent business facts.
- Implementation needs to change runtime auth/session semantics.
- A route contract is unclear and cannot be determined from existing tests/source.
- Tests would need full payload snapshots or sensitive row data to pass.

## State-Machine Impact

- Row260 remains `planning-closed`.
- Row261 closes as `planning-closed`.
- Row262 is inserted as `pending`.
- No module closure changes to `closed`.
- Production API/browser evidence remains deferred.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term architecture docs change in this design slice because no API behavior, runtime auth, business rule, worker, read model, permission or state-machine contract changed.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable in this design slice; Row262 may reuse service fakes but should not change service behavior.
3. API contract tests: applicable; Row262 should add a focused API contract harness test.
4. Read model/cache/background job tests: applicable to future assertions for refreshing/fresh/cache/readiness metadata and no false-fresh behavior.
5. Frontend component and interaction tests: still deferred; this is API contract design, not browser hydration.
6. End-to-end business-flow integration tests: not applicable to this design slice; Row262 should remain GET-only/read-shape focused.
7. Existing feature regression tests: applicable; Row262 should protect existing response envelopes and auth guard behavior.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command is executed in this planning/design slice.
