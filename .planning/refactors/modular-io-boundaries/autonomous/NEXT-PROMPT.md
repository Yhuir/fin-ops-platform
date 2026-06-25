# Next Prompt

Continue after `server-py:tax-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:tax-route-owner-local-closure-audit`.
- Row374 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-route-owner-local-closure-audit-2026-06-25.md`.
- Tax offset month/summary/calculate/plan-save/import-job/certified-imports list and certified import preview/confirm HTTP mapping now lives in `TaxApiRoutes.route(...)`.
- No `_handle_api_tax*` callbacks remain in `backend/src/fin_ops_platform/app/server.py`.
- Tax module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:tax-route-owner-local-closure-audit` is complete:

- audited remaining tax `Application` surfaces after route callback collapse;
- classified the remaining tax surfaces as composition-root, auth/session, body/import-job, runtime/query/read-model/cache/worker/source-version or scope-adapter ports;
- confirmed local tax `server.py` route-owner support is accounted for;
- selected cost statistics route-owner audit as the next local-first boundary.

## Next Boundary

`server-py:cost-statistics-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/state-machine.md`
   - `docs/modules/cost-statistics/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining cost statistics `Application` route surfaces:
   - direct `/api/cost-statistics*` dispatch branches;
   - `_handle_api_cost_statistics*` callbacks;
   - export query parsing and file response ports;
   - project scope normalization/error mapping;
   - read model/query/runtime/cache/worker provider surfaces.
4. Decide whether cost statistics callbacks are thin enough for route-owner callback collapse or whether a service/facade extraction is required first.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim cost statistics module/global closure unless all local and evidence gates are explicitly satisfied.
- Do not weaken `active/all` scope grammar, freshness/fail-closed behavior, export limits, transaction detail errors, or project detail contracts.
- Do not broaden into unrelated domains.
