# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:transaction-persist-repository-owner-split` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:transaction-persist-repository-owner-split`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction and transaction persist repository owner split are locally complete.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:command-repository-snapshot-adapter-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-transaction-persist-repository-owner-split.md`
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

- Audit the app-level callback repository and snapshot merge/apply helpers:
  - `_workbench_relation_command_repository(...)`
  - `_save_workbench_relation_command_snapshot(...)`
  - `_apply_workbench_relation_command_snapshot(...)`
  - `_relation_history_touches_cases(...)`
- Decide whether the next implementation boundary should extract these helpers into an explicit adapter/port, split only snapshot apply logic, or defer to another narrower persist/schedule helper boundary.
- Classify retained app-level logic as dependency assembly, implementation-pending, compat-only/quarantined, production-evidence-deferred, or blocked-by-human-gate.
- Produce an analysis file and insert the selected next boundary before Go candidates.

Forbidden:

- Do not implement adapter extraction during this audit slice.
- Do not change relation business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- One analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:command-repository-snapshot-adapter-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
