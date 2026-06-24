# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset`.
- `WorkbenchActionApiRoutes` owns the modern action delegation for exception preview/apply, confirm-link preview/submit, mark-exception, cancel-link, withdraw-link preview/submit, cash special actions, update-bank-exception, OA-bank-exception, personal advance repayment, cancel-exception, ignore-row and unignore-row.
- Final residual audit found no remaining app-owned direct `WorkbenchWriteFacade` action delegation in the audited modern Workbench action surface.
- Cancel-exception no-op live dispatch branch is removed.

## Next Boundary

`server-py:modern-workbench-action-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-cancel-exception-live-dispatch-noop-cleanup.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-final-residual-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
   - `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit whether the modern Workbench action route-owner slice set has local closure evidence.
- Verify route owner coverage, legacy quarantine, direct facade absence, HTTP responsibility split, tests and docs are accounted for.
- Document any remaining server ownership gaps outside this action route-owner slice set.
- Select the next bounded modular IO boundary based on evidence.

Do not:

- Do not change runtime behavior in this audit slice unless a clear guard/documentation fix is required for state consistency.
- Do not move new routes, remove wrappers, alter response shapes, or change route behavior in this audit slice.
- Do not mark global Workbench relation, read model, worker or Go admission closure.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- New analysis file documenting local closure evidence and remaining gaps.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if ownership facts change.
- Targeted static verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified local closure audit slice: local route-owner evidence is documented, remaining gaps and next boundary are explicit, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
