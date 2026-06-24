# Post Workbench High-Row Query Plan Next Boundary Selection - 2026-06-25

**Boundary:** `planning:post-workbench-high-row-query-plan-next-boundary-selection`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `production:read-model-unauthenticated-api-status-shape-classification-runbook`

## Goal

Reconcile Row257 Workbench high-row PostgreSQL evidence and select the next safe boundary for the remaining API/browser/module closure gaps.

This slice does not claim Workbench, module or global closure.

## Inputs Reviewed

- `analysis/production-workbench-read-model-high-row-query-plan-read-only-runbook-2026-06-25.md`
- `analysis/production-read-model-shadow-read-rehearsal-read-only-runbook-2026-06-25.md`
- `analysis/production-read-model-public-page-shell-smoke-runbook-2026-06-25.md`
- `analysis/production-read-model-authenticated-api-response-shape-smoke-runbook-2026-06-25.md`
- `analysis/read-model-authenticated-api-browser-smoke-runbook-selection-2026-06-25.md`
- `backend/src/fin_ops_platform/tools/http_slo_probe.py`
- `backend/src/fin_ops_platform/app/server.py`
- route/auth references surfaced by `rg`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

## Reconciled Row257 Evidence

Row257 proved:

- `/health/ready` stayed ready before and after.
- Active Workbench generations are bounded:
  - active metadata rows: 3491;
  - largest active scope: 1624 rows.
- Physical historical Workbench tables are large:
  - `workbench_rows=654911`;
  - `workbench_group_rows=729629`.
- Representative active page-like Workbench row/group-row queries use generation/scope indexes and EXPLAIN completed.
- Row255 `workbench_read_models` timeout is best classified as broad load-all/snapshot evidence gap, not proof that active page-like queries are unindexed.

Row257 did not prove:

- authenticated API response shapes;
- browser hydration/data behavior;
- export/detail flows;
- operation-barrier behavior;
- Workbench module closure;
- global closure.

## Candidate Boundary Review

| Candidate | Decision | Reason |
| --- | --- | --- |
| Final closure audit | Rejected | Authenticated API, browser and module-specific closure gaps remain open. |
| Authenticated HTTP SLO retry | Rejected for now | Row252 already proved no non-secret `FIN_OPS_HTTP_SLO_*` auth config exists. Retrying would reproduce `auth_missing`. |
| Browser data smoke | Deferred | Public shell is proven, but data/API auth remains unresolved. Browser data smoke without auth would mostly prove shell load or unauthenticated denial. |
| In-process Flask test client smoke | Rejected | The backend is not a Flask app; `Application` is served by `ThreadingHTTPServer` / `BaseHTTPRequestHandler`. There is no existing Flask `test_client` to reuse. |
| Build a new direct route harness | Deferred | Useful later, but creating a new harness is implementation work and should follow a clearer contract. The next step should use existing tooling first. |
| Unauthenticated API status/shape classification with existing `http_slo_probe` | Accepted | It uses existing read-only GET probe definitions, can run without auth by explicit `--allow-unauthenticated`, records status/content metadata and extracted read-model status without storing response bodies, and can classify which API surfaces are public, denied, 404, HTML-routed, refreshing or fresh. This does not prove authenticated API closure, but it materially narrows the API gap without secrets or mutation. |

## Selected Boundary

Select `production:read-model-unauthenticated-api-status-shape-classification-runbook`.

The next boundary must write and execute a bounded production runbook that:

1. Uses `/health/ready` pre/post checks.
2. Uses `fin_ops_platform.tools.http_slo_probe` with:
   - `--allow-unauthenticated`;
   - API probes only, not page probes;
   - one warmup and one measured iteration;
   - no response body storage.
3. Treats non-200 statuses as classification evidence, not as test failure.
4. Records:
   - probe count;
   - status-code distribution;
   - content types;
   - extracted `read_model_status`, `cache_status`, `refresh_enqueued` where available;
   - which probes are auth-blocked, public, missing, HTML-routed or refreshing.
5. Does not print tokens, cookies, env values, response bodies, payload rows or secrets.
6. Performs no deploy, restart, requeue, repair, replay, DB write, queue/readiness mutation or `--apply`.

## Why This Is The Highest-Risk Safe Next Step

- It directly addresses the next open closure class: API surface evidence.
- It avoids the known blocker from Row252 by not requiring auth.
- It does not pretend unauthenticated output proves authenticated behavior.
- It uses the existing default API probe inventory, which already covers Workbench, bank details, pending invoices, invoice usage, OA pending payments, output collections, tax, cost, no-OA, batch accounting, turnover, ETC, imports and search.
- It may reveal a smaller set of endpoints that can already provide shape/freshness evidence without auth, and a precise set that remain auth-blocked.

## State-Machine Impact

- Row257 remains `production-controlled`.
- Row258 closes as `planning-closed`.
- Row259 should be inserted as `pending`.
- No module closure changes to `closed`.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `prompts/04-master-goal-controller.md`.

No module docs or long-term architecture docs change in this planning slice because it only selects the next evidence boundary.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: applicable to the next boundary as unauthenticated status/shape classification, but not final authenticated API proof.
4. Read model/cache/background job tests: applicable as extracted `read_model_status` / `cache_status` / refresh metadata where APIs return JSON.
5. Frontend component and interaction tests: still open; not changed in this planning slice.
6. End-to-end business-flow integration tests: still open; this selects a narrower API classification step first.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command is executed in this planning slice.
