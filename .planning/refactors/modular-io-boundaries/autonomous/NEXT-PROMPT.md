# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:turnover-local-pair-snapshot-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:turnover-local-pair-snapshot-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Turnover primary builders and `TurnoverLedgerLocalClosureConnection` now use an explicit `TurnoverLedgerLocalPairSnapshotPort` instead of broad pair service injection.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:settings-data-reset-pair-service-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-local-pair-snapshot-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/settings/README.md`
   - `docs/modules/settings/state-machine.md`
   - `docs/modules/settings/tests.md`
4. Inspect:
   - `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_settings_data_reset_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `SettingsDataResetService`, `workbench_pair_relation_service`, `save_workbench_pair_relations`, `clear`, `reset`, `pair_relation_service`, and settings data reset tests.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit whether `SettingsDataResetService(workbench_pair_relation_service=...)` is a legitimate reset boundary, an old broad service leak, or a candidate for explicit reset/snapshot port extraction.
- Classify every settings reset pair relation interaction as removed, quarantined, compat-only, or requiring a follow-up implementation slice.
- Determine whether the next action should be an implementation slice or final local closure/defer accounting.
- Preserve data reset semantics, relation persistence semantics, API response shape, read model freshness contracts, dirty scopes and operation barriers.
- Do not mark the module closed unless local evidence proves all implementation gaps are closed.

Forbidden:

- Do not change settings reset behavior during this audit slice unless the analysis proves a tiny safe guard/doc fix is required.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow analysis/accounting slice.
- Updated queue/state/journal/next prompt.
- Targeted settings/workbench relation tests or static checks if changed, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:settings-data-reset-pair-service-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
