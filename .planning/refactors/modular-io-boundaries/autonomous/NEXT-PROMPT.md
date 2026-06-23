# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:command-repository-snapshot-adapter-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:command-repository-snapshot-adapter-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split and command repository snapshot adapter extraction are locally complete.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:pair-relation-persist-schedule-helper-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-command-repository-snapshot-adapter-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
5. Use CodeGraph for `_persist_workbench_pair_relations`, `_schedule_workbench_pair_relation_persist`, `_persist_workbench_pair_relations_in_background`, `_restore_workbench_pair_relation_snapshot`, `_workbench_write_facade`, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit remaining app-level pair relation persist/schedule/background/restore helpers and WorkbenchWriteFacade callback wiring.
- Decide the next narrow boundary:
  - extract a persist/schedule adapter;
  - split background scheduling first;
  - split restore snapshot helper;
  - or defer a broad relation lifecycle migration if the slice is too large.
- Classify retained app logic as dependency assembly, implementation-pending, compat-only/quarantined, production-evidence-deferred, or blocked-by-human-gate.

Forbidden:

- Do not implement persist/schedule helper extraction during this audit slice.
- Do not change relation business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- One analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:pair-relation-persist-schedule-helper-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
