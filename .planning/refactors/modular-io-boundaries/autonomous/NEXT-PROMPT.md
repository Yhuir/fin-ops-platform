# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:repository-port-and-sql-owner-split-plan`
- Last status: `closed-autonomous`
- The read model manifest covers the 14 App Status read models and is guarded against App Status registry, worker registry, RabbitMQ dispatch, scope policy, force refresh smoke contract, operation barrier target drift, and `PostgresReadModelRepository` repository port owner drift.

## Next Boundary

`read-models:workbench-active-generation-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/architecture/persistence-and-read-models.md`
   - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
4. Use CodeGraph for `PostgresReadModelRepository.get_workbench_view`, `get_workbench_summary`, `get_workbench_groups_page`, `get_workbench_group_detail`, `get_workbench_row_detail`, `get_workbench_refresh_status`, `WorkbenchQueryFacade`, `WorkbenchSqlProjectionBuilder`, and Workbench active generation helpers.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-active-generation-contract.md`.
6. If implementation starts in that boundary, keep it to Workbench active generation contract tests, manifest owner refinement, or one tiny guard. Do not rewrite Workbench matching, worker rebuild, route handlers, Go/Fiber, Go Worker, or production state.

## Stop Condition

Complete one narrow verified Workbench active-generation contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
