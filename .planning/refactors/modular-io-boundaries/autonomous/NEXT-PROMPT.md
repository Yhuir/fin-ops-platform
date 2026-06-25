# Next Prompt

Continue after `server-py:cost-statistics-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:cost-statistics-route-callback-collapse`.
- Row376 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-cost-statistics-route-callback-collapse-2026-06-25.md`.
- `/api/cost-statistics*` HTTP dispatch/query parsing now lives in `CostStatisticsApiRoutes.route(...)`.
- App-owned `_handle_api_cost_statistics*` callbacks were removed from `backend/src/fin_ops_platform/app/server.py`.
- Cost statistics module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:cost-statistics-route-callback-collapse` is complete:

- moved `/api/cost-statistics*` route dispatch/query parsing into `CostStatisticsApiRoutes.route(...)`;
- injected optional bool parsing as an explicit route-owner port;
- removed redundant app-owned cost statistics route callbacks;
- updated API/runtime tests and added a route-owner static Guard.

## Next Boundary

`server-py:cost-statistics-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-cost-statistics-route-callback-collapse-2026-06-25.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/state-machine.md`
   - `docs/modules/cost-statistics/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining cost statistics `Application` surfaces:
   - route factory/composition;
   - query/runtime/read-model/cache/warmup providers;
   - import scope adapters;
   - worker rebuild and derived lifecycle delegates;
   - file response and metrics ports.
4. Decide whether cost statistics local `server.py` route-owner support is accounted for, without claiming module/global production closure.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim cost statistics module/global closure unless all local and evidence gates are explicitly satisfied.
- Do not broaden into unrelated domains.
