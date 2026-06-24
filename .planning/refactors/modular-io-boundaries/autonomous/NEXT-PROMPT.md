# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:modern-workbench-action-route-owner-local-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:modern-workbench-action-route-owner-local-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset` as compat-only routes.
- `WorkbenchActionApiRoutes` owns modern action delegation for exception preview/apply, confirm-link preview/submit, mark-exception, cancel-link, withdraw-link preview/submit, cash special actions, update-bank-exception, OA-bank-exception, personal advance repayment, cancel-exception, ignore-row and unignore-row.
- Literal search found no remaining direct `_workbench_write_facade().` action call sites in `server.py`, `routes_workbench_actions.py` or `routes_legacy_workbench_actions.py`.
- Modern action route-owner local closure is accounted for, but Workbench/server.py/read model/global module closure remains open.

## Next Boundary

`server-py:workbench-row-detail-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-local-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-final-residual-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/reconciliation-workbench/implementation-notes.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/workbench_query_facade.py`
   - `tests/test_workbench_sql_runtime.py`
   - `tests/test_workbench_query_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit `GET /api/workbench/rows/{row_id}` route ownership.
- Verify the current live/cache/SQL `WorkbenchQueryFacade` fallback order and no-write relation boundary.
- Classify `Application._handle_api_workbench_row_detail(...)`, `_get_api_workbench_row_detail_payload(...)`, `_workbench_row_detail_from_query_facade(...)` and `_workbench_row_detail_route_fallback_allowed(...)` responsibilities.
- Identify whether a narrow route-owner extraction is safe as the next implementation slice, and select that next boundary based on evidence.

Do not:

- Do not move the row detail route in this audit slice.
- Do not change row detail response shape, status codes, override application, fallback order, stale/fresh behavior, SQL runtime fallback semantics, frontend detail drawer behavior or tests except static/accounting guards.
- Do not change Workbench groups, refresh status, settings, active generation publishing, matching worker, read model queue, legacy `/workbench/actions/*`, relation write behavior or modern Workbench action behavior.
- Do not mark global Workbench relation, read model, worker or Go admission closure.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- New analysis file documenting row detail route-owner evidence, remaining gaps and selected next boundary.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if ownership facts change.
- Targeted static verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified row-detail route-owner audit slice: route/fallback/no-write evidence is documented, remaining gaps and next boundary are explicit, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
