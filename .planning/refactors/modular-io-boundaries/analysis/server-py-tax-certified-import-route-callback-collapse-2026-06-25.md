# server-py:tax-certified-import-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Collapse the remaining tax certified import preview/confirm HTTP callbacks into `TaxApiRoutes.route(...)`.

## Pre-Implementation Audit

The remaining callbacks owned adapter concerns:

- mutation-session authorization;
- multipart body parsing and upload DTO normalization for preview;
- JSON body parsing and `session_id` validation for confirm;
- import queue/idempotency metadata;
- import job response serialization;
- inline confirm fallback and `KeyError` response mapping.

The business behavior was already owned by:

- `TaxCertifiedImportApplicationService.preview_payload(...)`;
- `ImportProcessingService.execute_tax_certified_import_confirm(...)`;
- import job repository/queue helpers.

## Implementation

- Added tax certified import preview/confirm route branches to `TaxApiRoutes.route(...)`.
- Injected explicit platform ports:
  - multipart body loader;
  - preview payload provider;
  - import job processing gate;
  - import job enqueue port;
  - import job serializer;
  - inline confirm executor.
- Removed `_handle_api_tax_certified_import_preview(...)`, `_handle_api_tax_certified_import_confirm(...)` and `_execute_tax_certified_import_confirm(...)` from `server.py`.
- Removed the `UploadedCertifiedImportFile` import from `server.py`; upload DTO normalization now lives in the tax route owner.
- Extended static platform runtime Guards so migrated tax certified import callbacks cannot return to `server.py`.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_tax.py backend/src/fin_ops_platform/app/server.py tests/test_tax_offset_api.py tests/test_import_job_queue.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_import_job_queue.ImportJobRepositoryTests.test_tax_certified_import_confirm_queue_result_can_be_polled -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_tax_offset_read_plan_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_tax_certified_import_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`

## Deferred

- No production PostgreSQL/worker/App Status/browser evidence was run or claimed.
- Tax module/global closure is not claimed.

## Next Boundary

`server-py:tax-route-owner-local-closure-audit`
