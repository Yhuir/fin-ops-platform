# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:restore-pair-relation-snapshot-helper-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:restore-pair-relation-snapshot-helper-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split, command repository snapshot adapter extraction and non-transactional pair relation persist service extraction are locally complete.
- `_restore_workbench_pair_relation_snapshot(...)` is required by WorkbenchWriteFacade failure rollback paths and is not removable.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:pair-relation-rollback-restore-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-restore-pair-relation-snapshot-helper-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
5. Use CodeGraph for `_restore_workbench_pair_relation_snapshot`, `_workbench_write_facade`, WorkbenchWriteFacade rollback callbacks, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit rollback restore service for pair relation snapshots, suggested:
  - file: `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
  - class: `WorkbenchPairRelationRollbackRestoreService`
- Move behavior currently in `_restore_workbench_pair_relation_snapshot(...)`:
  - rehydrate `WorkbenchPairRelationService` from snapshot;
  - reconfigure exception application service after replacement;
  - best-effort save restored snapshot to state store when available;
  - preserve error swallowing behavior during rollback restore.
- Keep `server.py` as dependency assembly/wrapper only if temporary wrappers are required for WorkbenchWriteFacade callbacks.
- Add focused service tests and update static guards if app wrapper remains only as a delegate.

Forbidden:

- Do not migrate `_restore_workbench_exception_pair_snapshots(...)`, `_restore_workbench_exception_write_snapshots(...)`, or `_restore_batch_accounting_pair_relation_snapshot(...)` in this slice unless required by a narrow reusable dependency.
- Do not change relation business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Runtime code change scoped to pair relation rollback restore extraction.
- Focused service tests and guard updates.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted verification, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:pair-relation-rollback-restore-service-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
