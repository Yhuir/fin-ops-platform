# server-py:input-invoice-usage-read-route-owner-facade-extraction

Status: `local-implementation-closed`

## Scope

This slice moved selected non-OA-reverse input-invoice usage read HTTP mappings from `Application` into `InputInvoiceUsageApiRoutes`.

Moved:

- `GET /api/input-invoice-usage/rows`
- `GET /api/input-invoice-usage/filter-options`
- `GET /api/input-invoice-usage/invoices/{invoice_id}/detail`
- `GET /api/input-invoice-usage/bank-transactions/{bank_transaction_id}/detail`
- `GET /api/input-invoice-usage/oa/{oa_id}/detail`
- `GET /api/input-invoice-usage/rows/{row_id}/relation-details`
- `GET /api/input-invoice-usage/payment-status-rules`

Explicitly retained for later slices:

- `GET /api/input-invoice-usage/export-preview`
- `GET /api/input-invoice-usage/export`
- `PUT /api/input-invoice-usage/payment-status-rules`

SQL/read-model fresh-gate helper implementations were not rewritten.

## Implementation Evidence

- Added `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`.
- Added `InputInvoiceUsageApiRoutes` with explicit ports:
  - `query_service`
  - `rows_from_sql_read_model`
  - `all_rows_from_sql_read_model`
  - `relation_details_from_sql_read_model`
  - `json_response`
  - `input_usage_error_response`
- Added `Application._input_invoice_usage_routes(...)` as dependency assembly only.
- Removed selected read handlers from `server.py`.
- Preserved export preview/download and payment rules PUT handlers in `server.py`.
- Added route-owner inventory/static Guard coverage.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_input_invoice_usage.py backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_input_invoice_usage_api.py
```

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_usage_read_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_oa_reverse_routes_use_route_owner -v
```

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_rows_route_returns_aggregated_rows_with_filters_sort_and_pagination tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_filter_options_payment_rules_details_and_relation_routes tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_rows_and_relation_details_return_multi_relation_totals_for_oa_bank_and_invoice tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_bank_filter_options_and_invoice_date_sort_are_http_contract_fields tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_relation_details_use_input_invoice_usage_read_model_row_without_live_rebuild tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_relation_details_compare_source_versions_with_row_scope tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_export_preview_and_download_use_current_input_invoice_usage_filters tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_export_returns_refreshing_when_sql_read_model_is_not_fresh tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_preview_batch_and_missing_client_draft_routes_are_formal_workflow -v
```

## Docs Impact

`docs/modules/input-invoice-usage/implementation-notes.md` was updated because route ownership changed.

## Remaining Risk

Export download and payment rules PUT still have route handlers in `Application`; they are intentionally deferred. Real PostgreSQL/worker/App Status/browser/admin/write evidence remains final validation and was not run.

## Next Boundary

`server-py:input-invoice-usage-export-route-owner-audit`

Audit export preview/download handling next because it has XLSX bytes, content-disposition headers, refreshing payload mapping and audit side effects.
