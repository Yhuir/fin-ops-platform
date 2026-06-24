# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:modern-workbench-action-route-owner-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:modern-workbench-action-route-owner-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset`.
- Modern `/api/workbench/actions/*` and `/api/workbench/exception/*` wrappers still live in `server.py` and delegate to `WorkbenchWriteFacade` or `WorkbenchExceptionApplicationService`.
- The modern route-owner audit selected `/api/workbench/exception/preview` as the first narrow extraction target because it has no freshness guard, auth context, request timing, request id, relation write, operation barrier, or read model refresh coupling.

## Next Boundary

`server-py:workbench-exception-preview-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/workbench_exception_application.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Move `/api/workbench/exception/preview` payload/error mapping behind an explicit modern Workbench action route owner.
- Preserve current behavior exactly:
  - Invalid JSON remains handled by `Application._load_json_body(...)`.
  - `WorkbenchExceptionApplicationService.preview(payload)` remains the delegate.
  - `KeyError` maps to `404` with `error=workbench_row_not_found`.
  - `TypeError` and `ValueError` map to `400` with `error=invalid_workbench_exception_preview_request`.
  - Success maps to `200` with the preview payload.
- Keep `Application` as the HTTP dispatch and JSON body parser for this slice if that keeps the change narrower.
- Add or update a static guard proving the preview endpoint is no longer implemented as an app-owned business/error-mapping wrapper once extracted.

Do not:

- Do not move `/api/workbench/exception/apply` in the same slice.
- Do not move confirm/cancel/withdraw, cash special, bank exception, OA-bank exception, personal advance repayment, cancel exception, ignore, or unignore routes.
- Do not change response shapes, status codes, auth, freshness guard, idempotency, relation semantics, operation barrier behavior, read model refresh behavior, frontend API behavior, or legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- A route owner or route-owner method that owns the modern exception preview mapping.
- Updated `server.py` delegation.
- Updated `tests/test_platform_runtime_boundary_guards.py` if guard semantics change.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if behavior/ownership facts change.
- Targeted API/static verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified route-owner extraction slice for `/api/workbench/exception/preview`: behavior is preserved by tests, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
