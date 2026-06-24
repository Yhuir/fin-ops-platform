# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:residual-route-handler-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:residual-route-handler-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `server.py` residual audit found Workbench as the largest residual owner group.
- The next selected non-Go shared-boundary slice is `server-py:workbench-legacy-action-handler-quarantine-audit`.

## Next Boundary

`server-py:workbench-legacy-action-handler-quarantine-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-residual-route-handler-boundary-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit Workbench legacy action handlers in `server.py` before any code movement.
- Target functions include:
  - `_handle_workbench_confirm`
  - `_handle_workbench_difference`
  - `_handle_workbench_exception`
  - `_handle_workbench_offline`
  - `_handle_workbench_offset`
  - `_handle_legacy_workbench_exception_via_application`
  - `_handle_live_workbench_confirm_link`
  - `_handle_live_workbench_cancel_link`
  - `_handle_live_workbench_withdraw_link`
  - `_handle_live_workbench_mark_exception`
  - `_handle_live_workbench_update_bank_exception`
  - `_handle_live_workbench_oa_bank_exception`
  - `_handle_live_workbench_confirm_personal_advance_repayment`
  - `_handle_live_workbench_cancel_exception`
  - `_handle_workbench_ignore_row_payload`
  - `_handle_workbench_unignore_row_payload`
- For each target group, classify:
  - current route dispatch callers,
  - whether it writes canonical facts,
  - whether it triggers read model or worker side effects,
  - whether it delegates to `WorkbenchWriteFacade` or old reconciliation/ledger services,
  - current tests covering it,
  - target state: removed, route-owned delegate, compat-only, or blocked by caller/API evidence.
- Select exactly one next narrow implementation or follow-up audit boundary.
- Do not move, delete or rewrite runtime code in this audit slice.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.
- Do not change canonical Python runtime behavior in this audit slice.

Expected output:

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/` recording:
  - previous state,
  - handler classification table,
  - caller/test evidence,
  - target state per handler group,
  - next selected narrow boundary,
  - why no runtime code changed,
  - affected docs/tests,
  - seven-category test applicability,
  - state-machine impact.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- If test guard semantics change, update `tests/test_platform_runtime_boundary_guards.py`.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified Workbench legacy action handler quarantine audit slice: handler target states and caller/test evidence are recorded, exactly one next narrow boundary is pending, no runtime behavior changed, Go admission remains blocked, state-machine accounting is current, docs verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
