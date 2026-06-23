# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:pair-relation-persist-schedule-helper-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:pair-relation-persist-schedule-helper-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split and command repository snapshot adapter extraction are locally complete.
- The audit selected non-transactional pair relation persist service extraction as the next narrow implementation boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:pair-relation-persist-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-pair-relation-persist-schedule-helper-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_workbench_persist_scheduler.py`
5. Use CodeGraph for `_persist_workbench_pair_relations`, `_schedule_workbench_pair_relation_persist`, `_persist_workbench_pair_relations_in_background`, `_workbench_write_facade`, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit service for non-transactional pair relation persistence/scheduling, suggested:
  - file: `backend/src/fin_ops_platform/services/workbench_pair_relation_persist_service.py`
  - class: `WorkbenchPairRelationPersistService`
- Move behavior currently in:
  - `_persist_workbench_pair_relations(...)`
  - `_schedule_workbench_pair_relation_persist(...)`
  - `_workbench_pair_relation_persist_async_enabled(...)`
  - `_persist_workbench_pair_relations_in_background(...)`
- Keep `server.py` as dependency assembly/wrapper only if temporary wrappers are required for tests/callers.
- Preserve:
  - search cache clearing;
  - state store absence no-op;
  - changed-case snapshot selection;
  - pending case coalescing and version skip behavior;
  - sync execution when async env is disabled;
  - async `Thread(...).start()` behavior when enabled;
  - timing emission payload.
- Add focused service tests and update static guards if app wrappers remain only as delegates.

Forbidden:

- Do not include `_restore_workbench_pair_relation_snapshot(...)` in this slice.
- Do not migrate broader relation command lifecycle.
- Do not change relation business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Runtime code change scoped to pair relation persist service extraction.
- Focused service tests and guard updates.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted verification, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:pair-relation-persist-service-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
