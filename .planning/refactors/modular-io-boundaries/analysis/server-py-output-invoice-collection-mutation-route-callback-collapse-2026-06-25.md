# server-py:output-invoice-collection-mutation-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Move the remaining output invoice collection receipt preview/settings and lifecycle/receipt/red-relation mutation HTTP mapping out of `Application` and into `OutputInvoiceCollectionApiRoutes`.

This slice intentionally does not change SQL read-model fresh-gate helper behavior.

## Implementation

- Extended `OutputInvoiceCollectionApiRoutes.route(...)` to own:
  - `POST /api/output-invoice-collections/receipt-preview`
  - `GET|PUT /api/output-invoice-collections/receipt-settings`
  - `PUT /api/output-invoice-collections/rows/{row_id}/collection-status`
  - `PUT /api/output-invoice-collections/rows/{row_id}/collection-reminder`
  - `DELETE /api/output-invoice-collections/rows/{row_id}/collection-reminder/{reminder_id}`
  - `POST /api/output-invoice-collections/rows/{row_id}/red-invoice-relations`
  - `DELETE /api/output-invoice-collections/red-invoice-relations/{relation_id}`
  - `POST /api/output-invoice-collections/rows/{row_id}/receipts`
  - `POST /api/output-invoice-collections/receipts/{receipt_id}/void`
  - `POST /api/output-invoice-collections/receipts/{receipt_id}/reissue`
- Added explicit `load_json_body` route-owner port.
- Preserved `x-request-id` trace id propagation for lifecycle/receipt/red-relation mutations.
- Preserved `Idempotency-Key` / `idempotency-key` header mapping for receipt creation.
- Removed all remaining `_handle_api_output_invoice_collections*` callbacks from `server.py`.
- Removed shared `_output_invoice_collection_mutation(...)` from `server.py`.
- Extended static guard coverage so output collection route callbacks cannot return to `server.py`.

## Preserved Behavior

- Output collection lifecycle and receipt business behavior remains in `OutputInvoiceCollectionApiRoutes`, `OutputInvoiceCollectionLifecycleService` and `OutputInvoiceCollectionReceiptService`.
- Permission checks remain route/service-owned through `OARequestSession`.
- Structured `OutputInvoiceCollectionError` response mapping is unchanged.
- Freshness target response contracts for lifecycle/receipt writes are unchanged.
- SQL read-model fresh-gate helper implementation remains unchanged and app-owned for the next boundary.

## Tests And Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_output_invoice_collections.py backend/src/fin_ops_platform/app/server.py tests/test_output_invoice_collection_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_boundary_does_not_depend_on_redis_or_rabbitmq_clients -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`

## Docs Impact

Docs applicable. Updated module implementation notes and autonomous state files. Long-term product/API semantics did not change.

## Next Boundary

`server-py:output-invoice-collection-read-model-fresh-gate-service-extraction`

Output collection route ownership is now locally accounted for, but SQL read-model fresh gate/source-version/schema stale/all-rows/detail helper logic remains app-owned in `Application`. The next slice should extract that logic behind an explicit service/adapter, preserving fail-closed and refreshing semantics.
