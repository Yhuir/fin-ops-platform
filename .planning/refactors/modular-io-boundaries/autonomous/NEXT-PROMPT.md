# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-row-detail-route-owner-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-row-detail-route-owner-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `WorkbenchRowDetailApiRoutes` owns `GET /api/workbench/rows/{row_id}` payload/fallback orchestration.
- `Application._get_api_workbench_row_detail_payload(...)` is now a thin delegate; `Application` keeps dependency assembly and HTTP response mapping.
- Workbench/server.py/read model/global module closure remains open.

## Next Boundary

`server-py:workbench-group-detail-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-row-detail-route-owner-extraction.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_query_facade.py`
   - `tests/test_workbench_query_facade.py`
   - `tests/test_workbench_sql_runtime.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit `GET /api/workbench/groups/detail` ownership.
- Verify current HTTP parameter validation, `WorkbenchQueryFacade.group_detail(...)` delegation and freshness/status proof contract.
- Classify `Application._handle_api_workbench_group_detail(...)` responsibilities and identify whether a narrow route-owner extraction is safe.
- Select the next bounded group-detail route-owner implementation or follow-up audit boundary based on evidence.

Do not:

- Do not change group detail response shape, status codes, freshness/stale behavior, source-version proof, read model refresh enqueue behavior, frontend group drawer behavior or existing API tests.
- Do not change Workbench row detail, groups page, refresh status, settings, active generation publishing, matching worker, read model queue, legacy `/workbench/actions/*`, relation write behavior or modern Workbench action behavior.
- Do not mark global Workbench relation, read model, worker or Go admission closure.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- New analysis file documenting group detail route-owner evidence, remaining gaps and selected next boundary.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if ownership facts change.
- Targeted static/API verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified group-detail route-owner audit slice: group detail route/freshness/no-write evidence is documented, remaining gaps and next boundary are explicit, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
