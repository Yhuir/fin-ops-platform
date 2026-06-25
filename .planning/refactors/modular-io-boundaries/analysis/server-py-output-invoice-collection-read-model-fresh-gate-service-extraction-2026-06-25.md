# server-py:output-invoice-collection-read-model-fresh-gate-service-extraction

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Extract output invoice collection SQL read-model fresh gate, schema stale proof, source-version proof, all-rows aggregation and relation-detail fail-closed handling out of `Application`.

This is a local implementation boundary only. It does not claim output invoice collection module/global closure or production evidence closure.

## Implementation

- Added `OutputInvoiceCollectionReadModelFreshGateService`.
- `Application._get_output_invoice_collection_rows_from_sql_read_model(...)` now delegates to the fresh-gate service.
- `Application._get_output_invoice_collection_all_rows_from_sql_read_model(...)` now delegates to the fresh-gate service.
- `Application._get_output_invoice_collection_relation_details_from_sql_read_model(...)` now delegates to the fresh-gate service.
- Removed app-owned output collection helper implementation:
  - `_output_invoice_collection_sql_payload_requires_schema_refresh(...)`
  - `_get_invoice_relation_all_rows_from_sql_read_model(...)`
  - `_invoice_relation_scope_key_from_query(...)`
  - `_invoice_relation_refreshing_payload(...)`
- Removed the now-unused output detail-service import from `server.py`.
- Updated architecture allowlist from `server.py` to the output fresh-gate service.
- Added direct service tests for schema stale and source-version stale behavior.
- Preserved route-owner handling for dict-based refreshing all-rows payloads across filter options, export preview and export download.
- Extended runtime boundary guard so output fresh-gate helper logic cannot return to `server.py`.

## Preserved Behavior

- Missing SQL repository in SQL runtime still returns `read_model_status=refreshing`, `readModelStatus=refreshing` and enqueues refresh.
- Schema-stale rows still enqueue `api_schema_stale` and return refreshing.
- Non-fresh `refresh_status` still enqueues `api_stale` and returns refreshing.
- Source-version mismatch still enqueues `api_source_versions_stale` and includes stale reasons.
- Fresh rows still expose both `read_model_status=fresh` and `readModelStatus=fresh`.
- Refreshing all-rows payloads are not exported as empty workbooks: filter options/export preview return 202, while export download returns a structured 409 refresh error.
- Relation detail production fail-closed behavior is preserved through `OutputInvoiceCollectionReadModelDetailService`.
- Lifecycle overlay behavior remains owned by `OutputInvoiceCollectionApiRoutes` and `OutputInvoiceCollectionQueryService`.

## Tests And Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/output_invoice_collection_read_model_fresh_gate_service.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_output_invoice_collections.py tests/test_output_invoice_collection_read_model_fresh_gate_service.py tests/test_output_invoice_collection_api.py tests/test_platform_runtime_boundary_guards.py tests/test_read_model_architecture_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_read_model_fresh_gate_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_read_export_routes_use_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Docs Impact

Docs applicable. Updated module implementation notes and autonomous state files. Long-term product/API semantics did not change.

## Next Boundary

`server-py:output-invoice-collection-post-fresh-gate-local-closure-audit`

The next step should audit remaining output collection app-owned surfaces after route callback collapse and fresh-gate extraction. It must not claim global closure unless the audit proves no local implementation gap remains and explicitly defers only production PostgreSQL/worker/App Status/high-row/browser evidence.
