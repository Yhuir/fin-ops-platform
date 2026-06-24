# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-group-detail-route-owner-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-group-detail-route-owner-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `GET /api/workbench/groups/detail` freshness/source-version/read-model-status proof is already owned by `WorkbenchQueryFacade.group_detail(...)`.
- `Application._handle_api_workbench_group_detail(...)` still owns HTTP-level zone/group-id validation and response mapping.
- Workbench/server.py/read model/global module closure remains open.

## Next Boundary

`server-py:workbench-group-detail-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-group-detail-route-owner-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/workbench_query_facade.py`
   - `tests/test_workbench_query_facade.py`
   - `tests/test_workbench_sql_runtime.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Extract `GET /api/workbench/groups/detail` HTTP validation and facade response mapping behind an explicit route owner.
- Preserve `Application` as HTTP route registration/dependency assembly owner.
- Preserve `WorkbenchQueryFacade.group_detail(...)` as the freshness/source-version/read-model-status proof boundary.
- Preserve status codes, response payloads, stale behavior, source-version proof and refresh enqueue behavior.
- Keep the route owner read-only.

Do not:

- Do not change group detail response shape, status codes, freshness/stale behavior, source-version proof, read model refresh enqueue behavior, frontend group drawer behavior or existing API tests.
- Do not change Workbench row detail, groups page, refresh status, settings, active generation publishing, matching worker, read model queue, legacy `/workbench/actions/*`, relation write behavior or modern Workbench action behavior.
- Do not mark global Workbench relation, read model, worker or Go admission closure.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- Runtime extraction in `routes_workbench.py` / `server.py`.
- Updated analysis file documenting the implementation and preserved contract.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if ownership facts change.
- Targeted static/API verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified group-detail route-owner extraction slice: group detail HTTP validation/facade response mapping is behind an explicit read-only route owner, freshness/status behavior remains delegated to `WorkbenchQueryFacade.group_detail(...)`, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
