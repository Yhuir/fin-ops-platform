# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:command-repository-snapshot-adapter-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:command-repository-snapshot-adapter-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction and transaction persist repository owner split are locally complete.
- The audit selected explicit command repository snapshot adapter extraction as the next narrow implementation boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:command-repository-snapshot-adapter-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-command-repository-snapshot-adapter-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
5. Use CodeGraph for `_workbench_relation_command_repository`, `_save_workbench_relation_command_snapshot`, `_apply_workbench_relation_command_snapshot`, `_relation_history_touches_cases`, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit service/adapter for app runtime command repository snapshot application, suggested:
  - file: `backend/src/fin_ops_platform/services/workbench_relation_command_repository_adapter.py`
  - class: `WorkbenchRelationCommandRepositoryAdapter`
- Move the behavior currently in:
  - `_workbench_relation_command_repository(...)`
  - `_save_workbench_relation_command_snapshot(...)`
  - `_apply_workbench_relation_command_snapshot(...)`
  - `_relation_history_touches_cases(...)`
- Keep `server.py` as dependency assembly only.
- Preserve:
  - current snapshot load from runtime `WorkbenchPairRelationService`;
  - optional transaction repository `save_workbench_pair_relations(...)`;
  - changed-case merge semantics;
  - history replacement semantics for touched cases;
  - runtime mirror update behavior;
  - post-apply exception application service reconfiguration callback.
- Add focused unit tests for the adapter and a static guard that removed app-level helper methods do not return.

Forbidden:

- Do not migrate broader relation command service lifecycle.
- Do not remove app-level pair relation persist/schedule/background helpers in this slice.
- Do not change relation business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Runtime code change scoped to command repository snapshot adapter extraction.
- Focused adapter tests and static guard update.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted verification, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:command-repository-snapshot-adapter-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
