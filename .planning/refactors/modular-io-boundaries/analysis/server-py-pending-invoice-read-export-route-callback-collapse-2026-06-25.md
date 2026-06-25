# server-py:pending-invoice-read-export-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Move the pending invoice read/detail/candidate/export HTTP mapping out of `server.py` and into `PendingInvoiceApiRoutes.route(...)`, while leaving rules, attach-existing and income-status write callbacks for later slices.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-route-owner-audit-2026-06-25.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/state-machine.md`
- `docs/modules/pending-invoices/tests.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `tests/test_pending_invoice_api.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Implementation

- Added `PendingInvoiceApiRoutes.route(...)` for:
  - `GET /api/pending-invoices/rows`
  - `GET /api/pending-invoices/filter-options`
  - `GET /api/pending-invoices/invoice-candidates`
  - `POST /api/pending-invoices/invoice-candidates/batch`
  - `GET /api/pending-invoices/rows/{transaction_id}/relation-detail`
  - `GET /api/pending-invoices/bank-transactions/{bank_transaction_id}/detail`
  - `GET /api/pending-invoices/invoices/{invoice_id}/detail`
  - `GET /api/pending-invoices/oa/{oa_id}/detail`
  - `GET /api/pending-invoices/export-preview`
  - `GET /api/pending-invoices/export`
- Injected explicit route-owner platform ports for read-session resolution, JSON response mapping, JSON body loading, pending invoice error response mapping and export XLSX/audit response mapping.
- Replaced migrated direct dispatch in `server.py` with `_pending_invoice_routes().route(method, route_path, query, body, headers)`.
- Removed the migrated app-owned read/detail/candidate/export callbacks from `server.py`.
- Kept pending invoice rules, attach-existing and income-status write callbacks in `server.py` for a separate write-boundary audit.

## Guard

Added `PlatformRuntimeBoundaryGuardTests.test_pending_invoice_read_export_routes_use_route_owner` to require route-owner coverage for the migrated paths and reject reintroduced app-owned read/export callbacks.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_pending_invoices.py backend/src/fin_ops_platform/app/server.py tests/test_pending_invoice_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_pending_invoice_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`

## Deferred

- No pending invoice business rule, read-model freshness/source-version, attach-existing, rules, income-status or frontend API shape changed.
- No production PostgreSQL/worker/App Status/browser evidence was run or claimed.
- Pending invoice module/global closure is not claimed.

## Next Boundary

`server-py:pending-invoice-write-route-callback-audit`
