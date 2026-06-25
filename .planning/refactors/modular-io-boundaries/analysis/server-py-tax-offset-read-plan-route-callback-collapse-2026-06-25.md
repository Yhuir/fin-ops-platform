# server-py:tax-offset-read-plan-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Move tax offset month/summary/calculate/plan-save/import-job/certified-imports list HTTP mapping into `TaxApiRoutes.route(...)`.

## Implementation

- Added `TaxApiRoutes.route(...)`.
- Injected explicit platform ports for read session, mutation session, JSON body loading, actor id and certified import records payload.
- Moved route-owner mapping for:
  - `GET /api/tax-offset`
  - `GET /api/tax-offset/summary`
  - `POST /api/tax-offset/calculate`
  - `POST /api/tax-offset/plans`
  - `GET /api/tax-offset/certified-import/jobs/{import_job_id}`
  - `GET /api/tax-offset/certified-imports`
- Removed migrated app callbacks from `server.py`.
- Preserved certified import preview/confirm callbacks in `server.py` for a separate audit because they own multipart parsing and import queue/inline execution semantics.
- Added static route-owner Guard coverage.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_tax.py backend/src/fin_ops_platform/app/server.py tests/test_tax_offset_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_tax_offset_read_plan_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Deferred

- Certified import preview/confirm callbacks remain in `server.py`.
- No production PostgreSQL/worker/App Status/browser evidence was run or claimed.
- Tax module/global closure is not claimed.

## Next Boundary

`server-py:tax-certified-import-route-callback-audit`
