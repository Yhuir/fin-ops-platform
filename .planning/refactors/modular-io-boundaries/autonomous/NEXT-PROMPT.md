# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:pair-relation-persist-service-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:pair-relation-persist-service-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split, command repository snapshot adapter extraction and non-transactional pair relation persist service extraction are locally complete.
- `server.py` still owns `_restore_workbench_pair_relation_snapshot(...)`; that helper is rollback-oriented and was intentionally excluded from the persist service extraction.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:restore-pair-relation-snapshot-helper-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-pair-relation-persist-service-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `backend/src/fin_ops_platform/services/workbench_pair_relation_persist_service.py`
5. Use CodeGraph for `_restore_workbench_pair_relation_snapshot`, `_workbench_write_facade`, WorkbenchWriteFacade rollback callbacks, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit the rollback restore snapshot helper before any implementation.
- Classify `_restore_workbench_pair_relation_snapshot(...)` as removable, extractable, compat-only, or blocked.
- Identify all callbacks/callers that depend on restore behavior.
- Record whether restore belongs in an existing command repository adapter, a new rollback service, WorkbenchWriteFacade, or should remain temporarily compat-only.
- Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not migrate rollback restore in the audit slice unless the queue is explicitly split/advanced after analysis.
- Do not change relation business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice only unless the analysis proves a trivial no-code removal.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:restore-pair-relation-snapshot-helper-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
