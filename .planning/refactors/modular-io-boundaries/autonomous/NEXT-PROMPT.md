# Next Prompt

Continue after `server-py:cost-statistics-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:cost-statistics-route-owner-local-closure-audit`.
- Row377 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-cost-statistics-route-owner-local-closure-audit-2026-06-25.md`.
- `/api/cost-statistics*` HTTP dispatch/query parsing lives in `CostStatisticsApiRoutes.route(...)`.
- No `_handle_api_cost_statistics*` callbacks remain in `backend/src/fin_ops_platform/app/server.py`.
- Cost statistics module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:cost-statistics-route-owner-local-closure-audit` is complete:

- audited remaining cost statistics `Application` surfaces after route callback collapse;
- classified remaining surfaces as composition-root, query/runtime, source-version, persistence, cache, worker, warmup, import-scope or platform adapter ports;
- confirmed local cost statistics `server.py` route-owner support is accounted for;
- selected turnover ledger route-owner audit as the next local-first boundary.

## Next Boundary

`server-py:turnover-ledger-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-cost-statistics-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining turnover ledger `Application` route surfaces:
   - direct `/api/turnover-ledger*` dispatch branches;
   - `_handle_api_turnover_ledger*` callbacks;
   - read/export/tag-selection/relation-extra/confirm/withdraw groups;
   - write facade and stale precondition boundaries.
4. Decide whether to collapse a thin route group or extract a service/facade first.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change turnover ledger behavior during the audit.
- Do not weaken stale preconditions, operation barrier targets, Workbench relation command boundaries, export limits or `turnover_ledger` freshness semantics.
- Do not broaden into unrelated domains.
