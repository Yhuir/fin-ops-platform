# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:local-implementation-closure-and-production-evidence-defer` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:local-implementation-closure-and-production-evidence-defer`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Local closure cannot move to `production-evidence-deferred` while ETC repair/link/migration `persist_pair_relations` callback accounting is open.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:etc-repair-link-migration-persist-callback-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-local-implementation-closure-and-production-evidence-defer.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
   - `backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py`
   - `backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py`
   - `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`
   - relevant ETC tests and static guards.
5. Use CodeGraph/text search for `persist_pair_relations`, `_persist_pair_relations`, `relation_command_service`, `confirm_relation`, `update_relation_metadata_for_case_id`, `get_active_relation_by_case_id`, `HistoricalEtcRepairService`, `HistoricalEtcBusinessBatchMigrationService`, and `ExistingEtcBatchLinkService`.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit whether ETC repair/link/migration `persist_pair_relations` callbacks are still required.
- Classify callbacks as removable, explicit post-command persist boundary, compat-only test/tool wiring, or implementation gap requiring a port.
- Confirm command-service relation writes are mandatory before ETC local writes.
- Confirm old direct pair relation mutation fallback cannot return.
- Decide the next smallest boundary: implementation removal/port extraction, or local closure/defer accounting.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change ETC repair/link/migration behavior during this audit slice unless a tiny guard/doc fix is required.
- Do not mark `workbench_relation` production-evidence-deferred if any local implementation gap remains.

## Expected Output

- Narrow audit/accounting slice.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:etc-repair-link-migration-persist-callback-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
