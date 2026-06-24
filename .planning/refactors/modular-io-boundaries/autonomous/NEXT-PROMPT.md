# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-exception-apply-route-owner-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-exception-apply-route-owner-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset`.
- `WorkbenchActionApiRoutes` now owns `/api/workbench/exception/preview` payload/error mapping.
- `WorkbenchActionApiRoutes` now owns `/api/workbench/exception/apply` facade delegation, actor fallback, request-id forwarding and `exception_apply` action-name mapping.
- Modern `/api/workbench/actions/confirm-link/preview` and the other `/api/workbench/actions/*` wrappers still live in `server.py` and delegate to `WorkbenchWriteFacade`.

## Next Boundary

`server-py:workbench-confirm-link-preview-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-exception-apply-route-owner-extraction.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Move `/api/workbench/actions/confirm-link/preview` preview facade delegation and invalid-request mapping behind `WorkbenchActionApiRoutes`.
- Preserve current behavior exactly:
  - Invalid JSON remains handled by `Application._load_json_body(...)`.
  - `WorkbenchWriteFacade.preview_confirm_link(...)` remains the delegate.
  - `KeyError`, `TypeError`, and `ValueError` still map to HTTP 400 with `error="invalid_confirm_link_preview_request"`.
  - Successful preview still maps to HTTP 200 with the existing preview payload.
  - Response serialization remains through `Application._json_response(...)` for this slice unless a smaller reviewed route-owner helper preserves it exactly.
- Keep `Application` as HTTP dispatch, JSON body parser and response serializer for this slice if that keeps the change narrower.
- Add or update a static guard proving confirm-link preview facade/error mapping is no longer app-owned once extracted.

Do not:

- Do not move confirm submit, cancel, withdraw, cash special, bank exception, OA-bank exception, personal advance repayment, cancel exception, ignore, unignore, exception preview or exception apply routes in this slice.
- Do not change response shapes, status codes, auth, freshness guard, timing headers, idempotency, relation semantics, operation barrier behavior, read model refresh behavior, frontend API behavior, or legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- `WorkbenchActionApiRoutes` method that owns confirm-link preview facade delegation and invalid-request mapping.
- Updated `server.py` delegation.
- Updated `tests/test_platform_runtime_boundary_guards.py` if guard semantics change.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if behavior/ownership facts change.
- Targeted API/static verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified route-owner extraction slice for `/api/workbench/actions/confirm-link/preview`: behavior is preserved by tests, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
