# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- WorkbenchWriteFacade active relation reads, withdraw preview fallback, pair snapshots and cash special metadata mutations now go through explicit ports.
- WorkbenchWriteFacade no longer stores broad `_pair_relation_service`.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-write-facade-post-port-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-boundary-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-relation-read-snapshot-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for remaining WorkbenchWriteFacade relation dependencies, `_pair_relation_service`, `pair_relation_service=`, `WorkbenchWriteRelationReadSnapshotPort`, `WorkbenchWriteRelationSpecialMetadataMutationPort`, and relation command service usage.
6. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Re-audit WorkbenchWriteFacade after read/snapshot and special metadata ports.
- Decide whether remaining local gaps need more implementation before broader `workbench_relation` closure work.
- Classify constructor-level `pair_relation_service` usage as removable, port-factory-only, compat-only, or requiring a later boundary.
- Select the next smallest safe boundary.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed unless all full closure requirements are met.
- Do not change relation write semantics, cash special semantics, dirty scope semantics or read model refresh semantics in this audit slice.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-write-facade-post-port-local-implementation-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
