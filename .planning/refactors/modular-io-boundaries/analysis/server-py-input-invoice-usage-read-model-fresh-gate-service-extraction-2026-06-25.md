# server-py:input-invoice-usage-read-model-fresh-gate-service-extraction

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Extract input invoice usage SQL read-model fresh gate, schema stale proof, source-version proof, all-rows aggregation, relation-detail fail-closed handling and export row-page loading out of `Application`.

This is a local modular implementation boundary only. It does not claim input usage module closure, production browser closure, admin closure, write-apply closure or global refactor closure.

## Implementation

- Added `InputInvoiceUsageReadModelFreshGateService`.
- `Application._get_input_invoice_usage_rows_from_sql_read_model(...)` now delegates to the fresh-gate service.
- `Application._get_input_invoice_usage_all_rows_from_sql_read_model(...)` now delegates to the fresh-gate service instead of the shared app helper.
- `Application._get_input_invoice_usage_relation_details_from_sql_read_model(...)` now delegates detail fresh-gate/fail-closed behavior to the fresh-gate service.
- `InputInvoiceUsageExportService` now receives the fresh-gate service `export_page(...)` method as its row-page loader.
- Removed app-owned input usage helpers:
  - `_load_input_invoice_usage_export_page(...)`
  - `_input_invoice_usage_export_query_from_kwargs(...)`
  - `_input_invoice_usage_sql_payload_requires_schema_refresh(...)`
- `InputInvoiceUsageApiRoutes.filter_options(...)` now maps a refreshing SQL all-rows payload to HTTP `202` because the fresh-gate service returns payload dictionaries, not HTTP response objects.
- Output invoice collection behavior was intentionally left in the existing app-owned helper path and protected by a targeted regression.

## Boundary Evidence

- `server.py` now assembles explicit fresh-gate dependencies: repository, query service, SQL runtime requirement port, refresh enqueue port and expected source-version provider.
- Freshness decisions remain fail-closed:
  - missing SQL repository under SQL runtime returns `read_model_status=refreshing` and enqueues refresh;
  - schema-stale rows return refreshing and enqueue `api_schema_stale`;
  - non-fresh `refresh_status` returns refreshing and enqueue `api_stale`;
  - source-version mismatch returns refreshing, enqueue `api_source_versions_stale`, and includes stale reasons.
- The new service keeps HTTP mapping out of the service layer.
- The service does not import `app.auth`, read headers/cookies, or construct `Response`.
- Static guards now reject reintroducing the removed app-owned input usage fresh-gate helpers.

## Tests And Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/input_invoice_usage_read_model_fresh_gate_service.py tests/test_input_invoice_usage_read_model_fresh_gate_service.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_input_invoice_usage.py tests/test_read_model_architecture_guards.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_read_model_fresh_gate_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_usage_read_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_oa_reverse_routes_use_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_export_preview_and_download_use_current_input_invoice_usage_filters tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_export_returns_refreshing_when_sql_read_model_is_not_fresh tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_rows_route_returns_aggregated_rows_with_filters_sort_and_pagination tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_filter_options_payment_rules_details_and_relation_routes tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_preview_batch_and_missing_client_draft_routes_are_formal_workflow -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_export_service tests.test_input_invoice_usage_read_model_fresh_gate_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_export_preview_and_download_use_current_filter_without_pagination -v`

The first attempted output collection command used a stale test method name and failed at unittest discovery. The correct existing output collection regression above passed.

## Docs Impact

Docs applicable. Updated module implementation notes and autonomous state files. Long-term product/API semantics did not change; this was an internal service-boundary extraction.

## Next Boundary

`server-py:input-invoice-usage-post-fresh-gate-local-closure-audit`

The next step should audit remaining input usage app-owned surfaces after route-owner collapse and fresh-gate extraction. It must not claim module/global closure unless the audit proves no local implementation gap remains and explicitly defers only production PostgreSQL/worker/App Status/high-row/browser evidence.
