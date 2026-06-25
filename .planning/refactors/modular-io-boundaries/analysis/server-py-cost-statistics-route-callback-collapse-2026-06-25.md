# server-py:cost-statistics-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Move `/api/cost-statistics*` HTTP dispatch and query parsing from `Application.handle_request(...)` into `CostStatisticsApiRoutes.route(...)`.

This slice does not change cost attribution, project scope semantics, read model freshness, parent aggregate behavior, cache keys, worker fan-out, export row limits, XLSX generation or production behavior.

## Implementation

- Added `CostStatisticsApiRoutes.route(method, route_path, query)` for:
  - `GET /api/cost-statistics`;
  - `GET /api/cost-statistics/explorer`;
  - `GET /api/cost-statistics/export-preview`;
  - `GET /api/cost-statistics/export`;
  - `GET /api/cost-statistics/projects/{project_name}`;
  - `GET /api/cost-statistics/transactions/{transaction_id}`.
- Injected an explicit optional bool parser port for export flags.
- Changed `Application.handle_request(...)` to delegate `/api/cost-statistics*` to `self._cost_statistics_routes().route(...)`.
- Removed redundant app-owned route callbacks:
  - `_handle_api_cost_statistics(...)`;
  - `_handle_api_cost_statistics_explorer(...)`;
  - `_handle_api_cost_statistics_project(...)`;
  - `_handle_api_cost_statistics_export(...)`;
  - `_handle_api_cost_statistics_export_preview(...)`;
  - `_handle_api_cost_statistics_transaction(...)`.
- Removed the unused app-owned cost statistics project scope error helper.
- Updated SQL runtime tests away from the deleted private callbacks and onto the route-owner path.
- Added a static route-owner Guard preventing cost statistics route callbacks from returning to `server.py`.

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_cost_statistics.py backend/src/fin_ops_platform/app/server.py tests/test_cost_statistics_api.py tests/test_cost_statistics_sql_runtime.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_cost_statistics_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
```

All targeted checks passed.

## Seven-Category Test Accounting

- Business core unit tests: not applicable; cost attribution/business rules did not change.
- Service-layer tests: not applicable; services/repositories/worker behavior did not change.
- API contract tests: applicable and covered by `tests.test_cost_statistics_api`.
- Read model/cache/background job tests: applicable because the route path reaches SQL/runtime freshness gates; covered by `tests.test_cost_statistics_sql_runtime`.
- Frontend component and interaction tests: not applicable; frontend behavior did not change.
- End-to-end business-flow integration tests: not applicable for this route-owner-only backend refactor.
- Existing feature regression tests: applicable and covered by cost statistics API/runtime tests plus route-owner Guard.

## Remaining Risk

Real PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain, production high-row behavior, production browser samples, admin evidence and controlled write evidence remain final validation scope. This slice only proves local route ownership and existing backend contracts.

## Next Boundary

`server-py:cost-statistics-route-owner-local-closure-audit`
