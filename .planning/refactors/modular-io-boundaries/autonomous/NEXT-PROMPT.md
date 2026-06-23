# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-bank-detail` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-bank-detail`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` current local implementation support slices are complete through the collaborator audit, but this is not full module closure.
- `workbench_relation` is selected as the next read model implementation pilot.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`read-models:workbench-relation-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-bank-detail.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `tests/test_workbench_relation_read_facade.py`
5. Use CodeGraph for structural lookup of `WorkbenchRelationReadFacade`, `WorkbenchRelationSqlProjectionBuilder`, `PostgresReadModelRepository` workbench relation methods, callers and impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add or identify a narrow `WorkbenchRelationReadModelRepositoryPort`.
- Expose only the relation read-model repository methods needed by facade/projection builder:
  - `get_workbench_relation_rows_by_ids`
  - `list_workbench_relation_rows`
  - `get_workbench_relation_groups_by_ids`
  - `workbench_relation_source_versions`
  - `save_workbench_relation_distribution`
  - `mark_workbench_relation_scope_empty`
- Wire `WorkbenchRelationReadFacade` and `WorkbenchRelationSqlProjectionBuilder` through that port where app wiring currently passes the broad read model repository.
- Add tests proving unrelated read model repository methods are not exposed through the port.
- Preserve candidate/linked/unlinked semantics, source-version behavior, freshness statuses, stale/missing enqueue behavior, payload shapes and refresh behavior.

Forbidden:

- Do not migrate the canonical relation write lifecycle in this slice.
- Do not move `app.workbench_pair_relations` write logic.
- Do not migrate pending invoice, OA pending, invoice usage/collection, no-OA, turnover, batch accounting, cost/tax/search in the same slice.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- Runtime code changes scoped to the repository port boundary.
- Focused tests for the port and existing workbench relation facade/projection behavior.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `read-models:workbench-relation-repository-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
