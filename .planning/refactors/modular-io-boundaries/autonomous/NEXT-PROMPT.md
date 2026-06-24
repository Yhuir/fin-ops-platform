# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-unignore-row-route-owner-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-unignore-row-route-owner-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset`.
- `WorkbenchActionApiRoutes` now owns `/api/workbench/exception/preview`, `/api/workbench/exception/apply`, `/api/workbench/actions/confirm-link/preview`, `/api/workbench/actions/confirm-link`, `/api/workbench/actions/mark-exception`, `/api/workbench/actions/cancel-link`, `/api/workbench/actions/withdraw-link`, cash special action mapping/delegation boundaries, `/api/workbench/actions/update-bank-exception`, `/api/workbench/actions/oa-bank-exception`, `/api/workbench/actions/confirm-personal-advance-repayment`, `/api/workbench/actions/cancel-exception`, `/api/workbench/actions/ignore-row`, and `/api/workbench/actions/unignore-row`.
- No known modern Workbench action in the audited set remains app-owned direct `WorkbenchWriteFacade` delegation.

## Next Boundary

`server-py:modern-workbench-action-route-owner-post-extraction-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-unignore-row-route-owner-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit the modern Workbench action route-owner extraction after unignore-row closure.
- Verify the audited modern action routes no longer have app-owned direct `WorkbenchWriteFacade` delegation in `Application`.
- Verify `Application` still owns only acceptable HTTP concerns for these routes: dispatch, JSON parse, freshness guard, auth/request context where already present, request timing where already present, and response serialization.
- Verify `LegacyWorkbenchActionRoutes` remains compat-only and does not import modern write/read model refresh boundaries.
- Decide the next bounded server ownership slice based on evidence.

Do not:

- Do not change runtime behavior in this audit slice unless a clear guard/documentation fix is required for state consistency.
- Do not move new routes, remove wrappers, remove the cancel-exception live-service no-op branch, or alter response shapes in this audit slice.
- Do not change response shapes, status codes, auth, freshness guard, timing headers, idempotency, relation semantics, operation barrier behavior, read model refresh behavior, frontend API behavior, or legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- New analysis file documenting post-extraction findings and the selected next boundary.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if ownership facts change.
- Targeted static verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified post-extraction audit slice: residual app-owned direct facade delegation state is documented, the next bounded server ownership slice is selected, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
