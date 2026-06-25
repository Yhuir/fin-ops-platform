# server-py:output-invoice-collection-read-export-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Move output invoice collection read/export/status/history/detail HTTP mapping out of `Application` and into `OutputInvoiceCollectionApiRoutes`.

This slice intentionally does not move lifecycle mutation callbacks, receipt preview/settings update callbacks, or SQL fresh-gate helper logic.

## Implementation

- Added `OutputInvoiceCollectionApiRoutes.route(...)` for:
  - `/api/output-invoice-collections/rows`
  - `/api/output-invoice-collections/filter-options`
  - `/api/output-invoice-collections/export-preview`
  - `/api/output-invoice-collections/export`
  - `/api/output-invoice-collections/status-rules`
  - `/api/output-invoice-collections/receipts/history`
  - `/api/output-invoice-collections/invoices/{invoice_id}/detail`
  - `/api/output-invoice-collections/bank-transactions/{bank_transaction_id}/detail`
  - `/api/output-invoice-collections/rows/{row_id}/relation-details`
- Injected explicit app/platform ports into the route owner:
  - read session resolver;
  - JSON response mapper;
  - XLSX response mapper;
  - structured `OutputInvoiceCollectionError` mapper.
- `Application.handle_request(...)` now delegates `/api/output-invoice-collections*` read/export/detail routes through `_output_invoice_collection_routes().route(...)` before falling through to remaining mutation callbacks.
- Removed migrated app-owned callbacks:
  - `_handle_api_output_invoice_collections_rows(...)`
  - `_handle_api_output_invoice_collections_filter_options(...)`
  - `_handle_api_output_invoice_collections_export_preview(...)`
  - `_handle_api_output_invoice_collections_export(...)`
  - `_handle_api_output_invoice_collections_invoice_detail(...)`
  - `_handle_api_output_invoice_collections_bank_transaction_detail(...)`
  - `_handle_api_output_invoice_collections_relation_details(...)`
  - `_handle_api_output_invoice_collections_status_rules(...)`
  - `_handle_api_output_invoice_collections_receipt_history(...)`
- Added `_output_invoice_collection_xlsx_response(...)` as an explicit platform response port for the route owner.
- Updated direct relation-detail API tests to exercise `Application.handle_request(...)` instead of deleted callbacks.
- Added static guard coverage that prevents migrated read/export callbacks from returning to `server.py`.

## Preserved Behavior

- Output collection SQL fresh-gate implementation remains unchanged.
- Relation detail production fail-closed behavior remains unchanged.
- XLSX `Content-Type`, `Content-Disposition`, CORS and `Access-Control-Expose-Headers` behavior is preserved through the explicit response port.
- Lifecycle mutation callbacks remain in `Application` for a later mutation-specific boundary.
- Receipt preview and receipt settings callbacks remain in `Application` for later audit/splitting.

## Tests And Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_output_invoice_collections.py backend/src/fin_ops_platform/app/server.py tests/test_output_invoice_collection_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_boundary_does_not_depend_on_redis_or_rabbitmq_clients -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_rows_route_returns_output_invoice_collection_read_model tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_export_preview_and_download_use_current_filter_without_pagination tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_export_rejects_row_count_over_contract_limit tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_detail_routes_require_output_collection_read_session tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_relation_details_require_sql_repository_in_production_without_live_rebuild tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_relation_details_use_fresh_sql_read_model_row_without_live_rebuild -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`
- `git diff --check`

## Docs Impact

Docs applicable. Updated module implementation notes and autonomous state files. Long-term product/API semantics did not change.

## Next Boundary

`server-py:output-invoice-collection-mutation-route-callback-audit`

The next step should audit remaining output collection mutation/receipt callbacks and decide whether to collapse them into the route owner directly or split receipt preview/settings/fresh-gate work first.
