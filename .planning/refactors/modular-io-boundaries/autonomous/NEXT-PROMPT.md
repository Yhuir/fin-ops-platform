# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:legacy-workbench-action-route-module-quarantine` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:legacy-workbench-action-route-module-quarantine`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` now owns old `/workbench/actions/confirm|difference|exception|offline|offset` payload mapping and reconciliation/ledger calls.
- `Application` no longer defines `_handle_workbench_confirm`, `_handle_workbench_difference`, `_handle_workbench_exception`, `_handle_workbench_offline`, or `_handle_workbench_offset`.
- Modern `/api/workbench/actions/*` wrappers remain `WorkbenchWriteFacade` delegates.
- The next selected non-Go shared-boundary slice is `server-py:legacy-workbench-exception-helper-dead-code-audit`.

## Next Boundary

`server-py:legacy-workbench-exception-helper-dead-code-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-legacy-workbench-action-route-module-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-legacy-action-handler-quarantine-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`
   - `backend/src/fin_ops_platform/services/workbench_exception_application_service.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit `_handle_legacy_workbench_exception_via_application(...)` after the old `/workbench/actions/*` route quarantine.
- Prove current caller evidence across app routes, tests and frontend API usage.
- Classify the helper as:
  - removable dead code,
  - compat-only helper with owner/caller/deletion condition, or
  - blocked by caller/API evidence.
- Select exactly one next narrow implementation or follow-up audit boundary.

Do not:

- Do not remove the helper in this audit slice unless the evidence is already complete and the implementation is smaller than the audit.
- Do not change modern `/api/workbench/exception/preview` or `/api/workbench/exception/apply` behavior.
- Do not change legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/` recording caller/test/API evidence, target state, next boundary, test applicability and state-machine impact.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- If guard semantics change, update `tests/test_platform_runtime_boundary_guards.py`.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified dead-code/compat audit slice for `_handle_legacy_workbench_exception_via_application(...)`: target state is recorded, exactly one next narrow boundary is pending, no unintended runtime behavior changes are made, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
