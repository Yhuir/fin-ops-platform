# Next Prompt

Continue after `server-py:cost-statistics-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:cost-statistics-route-owner-audit`.
- Row375 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-cost-statistics-route-owner-audit-2026-06-25.md`.
- `CostStatisticsApiRoutes` already owns cost statistics response mapping; `server.py` still owns direct `/api/cost-statistics*` dispatch/query parsing and thin `_handle_api_cost_statistics*` callbacks.
- Cost statistics module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:cost-statistics-route-owner-audit` is complete:

- audited `/api/cost-statistics*` dispatch branches and callbacks;
- confirmed the remaining callbacks are thin delegates to `CostStatisticsApiRoutes`;
- selected route callback collapse as the next local-first implementation boundary.

## Next Boundary

`server-py:cost-statistics-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-cost-statistics-route-owner-audit-2026-06-25.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/state-machine.md`
   - `docs/modules/cost-statistics/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
   - `tests/test_cost_statistics_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement the bounded route-owner collapse:
   - add route-owner dispatch for `/api/cost-statistics*`;
   - keep query parsing and optional bool parsing explicit;
   - remove redundant `_handle_api_cost_statistics*` callbacks from `server.py`;
   - preserve all existing payload/status/error/export contracts.
4. Add/update Guard coverage preventing cost statistics route callbacks from returning to `Application`.
5. Run targeted API/Guard/doc verification, then update docs/state and commit/push if verification passes.

## Stop Gates

- Do not change cost attribution, project scope semantics, read model freshness, parent aggregate, cache keys, worker fan-out, export row limits, XLSX generation or production behavior.
- Do not run production validation or mutation.
- Do not claim cost statistics module/global closure.
