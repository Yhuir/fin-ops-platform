# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:exception-restore-helper-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:exception-restore-helper-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split, command repository snapshot adapter extraction, non-transactional pair relation persist service extraction and pair relation rollback restore service extraction are locally complete.
- Remaining exception/pair/candidate/override rollback helpers are required recovery paths and are selected for explicit service extraction.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:exception-rollback-restore-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-exception-restore-helper-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
5. Use CodeGraph for `_restore_workbench_exception_pair_snapshots`, `_restore_workbench_exception_write_snapshots`, `_restore_workbench_exception_override_snapshots`, `_apply_workbench_exception_application`, personal advance rollback paths, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit exception rollback restore service, suggested:
  - file: `backend/src/fin_ops_platform/services/workbench_exception_rollback_restore_service.py`
  - class: `WorkbenchExceptionRollbackRestoreService`
- Move behavior currently in:
  - `_restore_workbench_exception_write_snapshots(...)`
  - `_restore_workbench_exception_pair_snapshots(...)`
  - `_restore_workbench_exception_override_snapshots(...)`
  - inline restore block in `_persist_workbench_exception_and_override_change(...)`
  - inline restore block in `_apply_workbench_exception_application(...)`
- Preserve exception case, pair relation, candidate match and override snapshot restoration semantics.
- Preserve best-effort `state_store.save_workbench_exception_cases(...)` behavior for exception/override rollback.
- Reuse the centralized pair relation replacement callback so cached pair relation persist service state remains consistent.
- Keep `server.py` as dependency assembly/wrapper only if temporary wrappers are required for WorkbenchWriteFacade callbacks.

Forbidden:

- Do not migrate unrelated batch-accounting restore behavior.
- Do not change relation or exception business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Runtime code change scoped to exception rollback restore extraction.
- Focused service tests and guard updates.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted verification, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:exception-rollback-restore-service-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
