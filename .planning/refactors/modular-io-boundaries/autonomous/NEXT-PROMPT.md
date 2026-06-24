# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:modern-workbench-action-route-owner-final-residual-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:modern-workbench-action-route-owner-final-residual-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset`.
- `WorkbenchActionApiRoutes` owns the modern action delegation for exception preview/apply, confirm-link preview/submit, mark-exception, cancel-link, withdraw-link preview/submit, cash special actions, update-bank-exception, OA-bank-exception, personal advance repayment, cancel-exception, ignore-row and unignore-row.
- Final residual audit found no remaining app-owned direct `WorkbenchWriteFacade` action delegation in the audited modern Workbench action surface.

## Next Boundary

`server-py:workbench-cancel-exception-live-dispatch-noop-cleanup`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-final-residual-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-cancel-exception-route-owner-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Remove the no-op `has_rows_for_month(month)` branch in `Application._handle_api_workbench_cancel_exception(...)`, where both branches currently call `_handle_live_workbench_cancel_exception(payload)`.
- Preserve current behavior exactly:
  - Invalid JSON remains handled by `Application._load_json_body(...)`.
  - Workbench write freshness guard remains in `Application`.
  - Existing `_handle_live_workbench_cancel_exception(payload)` response mapping remains unchanged.
  - Response shape, conflict behavior, affected scopes, operation projection and operation barrier behavior remain unchanged.
- Add or update a static guard proving the no-op branch is removed and cancel-exception still delegates through the route owner.

Do not:

- Do not move or alter other Workbench action routes.
- Do not change response shapes, status codes, auth, freshness guard, timing headers, idempotency, relation semantics, operation barrier behavior, read model refresh behavior, frontend API behavior, or legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- Simplified cancel-exception wrapper without the redundant live-service branch.
- Updated `tests/test_platform_runtime_boundary_guards.py` if guard semantics change.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if behavior/ownership facts change.
- Targeted API/static verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified cleanup slice for `/api/workbench/actions/cancel-exception`: behavior is preserved by tests, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
