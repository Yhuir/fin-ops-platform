# server-py:pending-invoice-write-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Move the remaining pending invoice rules, attach-existing and income-status HTTP mapping out of `server.py` and into `PendingInvoiceApiRoutes.route(...)`.

## Implementation

- Added write-session and persist-state platform ports to `PendingInvoiceApiRoutes`.
- Added route-owner mapping for:
  - `GET /api/pending-invoices/rules`
  - `PUT /api/pending-invoices/rules`
  - `POST /api/pending-invoices/rows/{transaction_id}/attach-existing-invoice/preview`
  - `POST /api/pending-invoices/rows/{transaction_id}/attach-existing-invoice`
  - `POST /api/pending-invoices/attach-existing-invoices/preview`
  - `POST /api/pending-invoices/attach-existing-invoices`
  - `PUT /api/pending-invoices/rows/{transaction_id}/income-status`
  - `PUT /api/pending-invoices/income-statuses`
- Removed migrated pending invoice app callbacks from `server.py`.
- Preserved existing adapter semantics:
  - body parsing happens before write-session resolution;
  - rules update does not call persist-state;
  - attach confirm persists on success, `PendingInvoiceError` and unexpected exception;
  - income-status update persists on success and unexpected exception, but not `PendingInvoiceError`.
- Extended static platform runtime boundary guards for pending invoice write routes.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_pending_invoices.py backend/src/fin_ops_platform/app/server.py tests/test_pending_invoice_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_pending_invoice_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_pending_invoice_write_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`

## Deferred

- No production PostgreSQL/worker/App Status/browser evidence was run or claimed.
- Pending invoice module/global closure is not claimed.

## Next Boundary

`server-py:pending-invoice-route-owner-local-closure-audit`
