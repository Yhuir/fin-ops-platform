# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:settings-data-reset-pair-service-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:settings-data-reset-pair-service-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Settings data reset relation clearing/filtering is a legitimate reset boundary, but `SettingsDataResetService` still accepts broad pair service.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:settings-data-reset-pair-snapshot-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-settings-data-reset-pair-service-boundary-audit.md`
   - `docs/modules/settings/README.md`
   - `docs/modules/settings/state-machine.md`
   - `docs/modules/settings/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_settings_data_reset_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `SettingsDataResetService`, `workbench_pair_relation_service`, `_pair_relations`, `save_workbench_pair_relations`, `RESET_OA_AND_REBUILD_ACTION`, and settings data reset pair relation tests.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit settings data reset pair snapshot/save port.
- Remove broad `workbench_pair_relation_service` from `SettingsDataResetService` constructor/storage.
- Preserve bank reset and invoice reset clearing behavior.
- Preserve OA reset filtering that removes OA-derived relations and keeps pure bank-invoice relations.
- Preserve deleted counts, protected targets, API response shape, read model cleanup, derived lifecycle fan-out and reset job behavior.
- Add or update static guard coverage proving `SettingsDataResetService` no longer accepts broad pair service.

Forbidden:

- Do not change relation command-service write semantics.
- Do not change reset action names, response fields, protected targets, job lifecycle or permission behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated queue/state/journal/next prompt.
- Targeted settings reset pair relation tests, static guard, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:settings-data-reset-pair-snapshot-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
