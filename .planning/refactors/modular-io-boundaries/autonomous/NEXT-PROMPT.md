# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-row-detail-route-owner-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-row-detail-route-owner-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- Modern Workbench action route-owner local closure is accounted for by `WorkbenchActionApiRoutes`; Workbench/server.py/read model/global module closure remains open.
- `GET /api/workbench/rows/{row_id}` behavior is locally tested for live path, route fallback, production PostgreSQL fallback blocking, stale cached row rejection and opaque OA SQL active generation fallback.
- Row detail fallback orchestration still lives in `Application._get_api_workbench_row_detail_payload(...)`, so route-owner extraction is the next bounded implementation slice.

## Next Boundary

`server-py:workbench-row-detail-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-row-detail-route-owner-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/workbench_query_facade.py`
   - `tests/test_workbench_sql_runtime.py`
   - `tests/test_workbench_query_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Extract Workbench row detail payload/fallback orchestration behind an explicit route owner.
- Preserve `Application` as HTTP route dispatch and response serializer only.
- Preserve the existing fallback order: ETC summary, live service, cached read models, `WorkbenchQueryFacade.row_detail(...)`, opaque OA fail-closed handling, and allowed legacy `WorkbenchApiRoutes.get_row_detail(...)` fallback.
- Preserve row override application, production PostgreSQL route fallback blocking and existing `404` response shape.
- Add or update static guards proving row detail fallback orchestration no longer lives in `Application` and the route owner does not write relation/read model queue state.

Do not:

- Do not change row detail response shape, status codes, override application, fallback order, stale/fresh behavior, SQL runtime fallback semantics, frontend detail drawer behavior or API tests.
- Do not change Workbench groups, refresh status, settings, active generation publishing, matching worker, read model queue, legacy `/workbench/actions/*`, relation write behavior or modern Workbench action behavior.
- Do not remove `WorkbenchApiRoutes.get_row_detail(...)` unless current call evidence and tests prove it is no longer needed in the same narrow slice.
- Do not mark global Workbench relation, read model, worker or Go admission closure.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- Runtime code extraction for row detail route owner only.
- Updated or new targeted guard tests plus existing row detail behavior tests.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if ownership facts change.
- Targeted Python tests, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified row-detail route-owner extraction slice: behavior tests and static guards pass, row detail fallback ownership is out of `Application`, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
