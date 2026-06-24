# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:legacy-workbench-exception-helper-dead-code-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:legacy-workbench-exception-helper-dead-code-audit`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset`.
- `Application` no longer defines the five old legacy Workbench action handlers.
- No-caller `_handle_legacy_workbench_exception_via_application(...)` has been removed.
- Modern `/api/workbench/actions/*` wrappers still live in `server.py` and delegate to `WorkbenchWriteFacade`.
- The next selected non-Go shared-boundary slice is `server-py:modern-workbench-action-route-owner-audit`.

## Next Boundary

`server-py:modern-workbench-action-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-legacy-workbench-exception-helper-dead-code-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-legacy-workbench-action-route-module-quarantine.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit modern Workbench action wrappers still in `server.py`, especially:
  - `_handle_api_workbench_confirm_link`
  - `_handle_api_workbench_confirm_link_preview`
  - `_handle_api_workbench_exception_preview`
  - `_handle_api_workbench_exception_apply`
  - `_handle_api_workbench_mark_exception`
  - `_handle_api_workbench_cancel_link`
  - `_handle_api_workbench_withdraw_link_preview`
  - `_handle_api_workbench_withdraw_link`
  - cash special, bank exception, OA-bank exception, personal advance repayment, cancel exception, ignore and unignore wrappers
- Classify each wrapper by HTTP/auth/freshness/timing responsibility, facade/application-service delegate, current tests, and target route owner.
- Select exactly one next narrow implementation or follow-up audit boundary.

Do not:

- Do not move runtime code in this audit slice unless the target is smaller than the audit and fully covered.
- Do not change modern Workbench API response shapes, status codes, auth, freshness guard, idempotency, relation semantics, operation barrier behavior, read model refresh behavior or frontend behavior.
- Do not change legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/` recording wrapper classification, tests, next boundary, test applicability and state-machine impact.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- If guard semantics change, update `tests/test_platform_runtime_boundary_guards.py`.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified route-owner audit slice for modern Workbench actions: target route-owner sequence is recorded, exactly one next narrow boundary is pending, no unintended runtime behavior changes are made, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
