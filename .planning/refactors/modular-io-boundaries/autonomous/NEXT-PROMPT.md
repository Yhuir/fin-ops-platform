# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:batch-accounting-pair-restore-helper-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:batch-accounting-pair-restore-helper-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- The audit confirmed `Application._restore_batch_accounting_pair_relation_snapshot(...)` is not removable because `BatchAccountingApiRoutes.submit(...)` depends on it for submit persist-failure rollback.
- The audit also confirmed the helper should no longer directly call `WorkbenchPairRelationService.from_snapshot(...)`; it should delegate to `WorkbenchPairRelationRollbackRestoreService` in in-memory mode so current no-state-store-save behavior is preserved.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:batch-accounting-pair-restore-service-delegation`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-batch-accounting-pair-restore-helper-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/batch-accounting/README.md`
   - `docs/modules/batch-accounting/tests.md`
   - `docs/modules/batch-accounting/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_batch_accounting.py`
   - `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
   - `tests/test_batch_accounting_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_restore_batch_accounting_pair_relation_snapshot`, `BatchAccountingApiRoutes`, `WorkbenchPairRelationRollbackRestoreService`, pair relation snapshot/restore wiring and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Keep `BatchAccountingApiRoutes` callback wiring intact.
- Make `Application._restore_batch_accounting_pair_relation_snapshot(...)` delegate to `WorkbenchPairRelationRollbackRestoreService.restore(...)`.
- Preserve existing batch-accounting behavior: restore in-memory pair relation service and reconfigure exception application service, but do not save rollback snapshot to state store from this route-local callback.
- Add or extend tests/guards proving the app helper no longer owns direct `WorkbenchPairRelationService.from_snapshot(...)` restore behavior.

Recommended shape:

- Add a small app dependency assembly helper for batch-accounting rollback restore that constructs `WorkbenchPairRelationRollbackRestoreService` with `state_store=None`.
- Call `.restore(snapshot, changed_case_ids=[])` from `_restore_batch_accounting_pair_relation_snapshot(...)`.
- Extend `tests/test_platform_runtime_boundary_guards.py` to guard the batch-accounting wrapper and factory.
- Run the existing submit persist-failure rollback API test if present; add a focused regression only if existing coverage does not prove rollback behavior.

Forbidden:

- Do not change batch-accounting submit/withdraw business rules.
- Do not add withdraw rollback behavior in this slice.
- Do not change API payloads, write semantics, dirty scope semantics, read model refresh semantics or production state.
- Do not persist rollback snapshot from this route-local callback unless a separate behavior-changing slice is planned and tested.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Narrow implementation slice.
- Updated analysis/accounting file for the implementation.
- Updated docs/state/queue/journal/next prompt.
- Targeted tests, app check if needed, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:batch-accounting-pair-restore-service-delegation` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
