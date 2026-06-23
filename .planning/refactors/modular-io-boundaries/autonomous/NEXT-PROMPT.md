# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:settings-data-reset-pair-snapshot-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:settings-data-reset-pair-snapshot-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open` until closure/defer accounting proves otherwise.
- `SettingsDataResetService` now uses explicit `SettingsDataResetPairSnapshotPort` instead of broad pair service injection.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:local-implementation-closure-and-production-evidence-defer`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read all `workbench-relations-*` analysis files from the current pilot sequence, especially the latest closure/accounting files.
4. Read:
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
5. Inspect remaining `_workbench_pair_relation_service` references in `backend/src/fin_ops_platform/app/server.py`, service modules, tools and tests.
6. Use CodeGraph/text search for remaining direct pair service reads/writes, `pair_relation_service=`, `_workbench_pair_relation_service`, `save_workbench_pair_relations`, `load_workbench_pair_relations`, `replace_pair_relation_service`, `persist_pair_relations`, and closure/defer notes.
7. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Decide whether local `workbench_relation` implementation support slices can be marked `production-evidence-deferred` or whether more local implementation slices are required.
- Classify every remaining broad pair relation service use as legitimate explicit boundary, compat-only, test-only, tool-only, pending implementation gap, or production evidence gap.
- Confirm old paths cannot write canonical relation facts, dirty scopes, outbox, read model readiness, cache or App Status outside approved boundaries.
- Confirm Go hot-path admission remains blocked unless the documented prerequisites are actually satisfied.
- Do not perform production writes, DB writes, queue mutation, worker replay or secret reads.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not mark `workbench_relation` closed unless every local implementation requirement and environment evidence/defer rule is explicitly satisfied.
- Do not hide remaining local implementation gaps as production evidence defer.

## Expected Output

- Narrow closure/defer analysis slice.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:local-implementation-closure-and-production-evidence-defer` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
