# server-py:output-invoice-collection-post-fresh-gate-local-closure-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining output invoice collection `Application` surfaces after route-owner callback collapse and read-model fresh-gate service extraction.

This is an analysis boundary only. It does not claim output collection module/global closure or production PostgreSQL/worker/App Status/high-row/browser closure.

## Evidence Reviewed

- `analysis/server-py-output-invoice-collection-mutation-route-callback-collapse-2026-06-25.md`
- `analysis/server-py-output-invoice-collection-read-model-fresh-gate-service-extraction-2026-06-25.md`
- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/output-invoice-collections/state-machine.md`
- `docs/modules/output-invoice-collections/tests.md`
- CodeGraph context for output invoice collection `Application` surfaces.
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_read_model_fresh_gate_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_output_invoice_collection_api.py`

## Remaining Application Surfaces

The remaining output collection references in `server.py` are accounted for as explicit composition-root, platform or provider ports:

- `_output_invoice_collection_service(...)`: dependency assembly for `OutputInvoiceCollectionQueryService`, relation facade, OA projection and lifecycle repository.
- `_output_invoice_collection_routes(...)`: route-owner composition and explicit port injection for read-model providers, session resolver, JSON/XLSX/error responses and body loading.
- `_output_invoice_collection_read_model_fresh_gate(...)`: composition of `OutputInvoiceCollectionReadModelFreshGateService` with explicit repository, query service, runtime requirement, refresh enqueue and source-version provider dependencies.
- `_output_invoice_collection_xlsx_response(...)` and `_output_invoice_collection_error_response(...)`: HTTP adapter helpers that construct response objects at the application boundary.
- `_get_output_invoice_collection_all_rows_from_sql_read_model(...)`, `_get_output_invoice_collection_rows_from_sql_read_model(...)`, `_get_output_invoice_collection_relation_details_from_sql_read_model(...)`: provider adapters that delegate directly to the fresh-gate service.
- `_output_invoice_collection_expected_source_versions(...)`: source-version provider that composes canonical output source versions with Workbench relation source versions from the output read repository.
- `_enqueue_output_invoice_collection_read_model_refresh(...)`: refresh gateway port; it delegates to `ReadModelRefreshGateway.enqueue_one(...)`.
- `_resolve_output_invoice_collection_read_session(...)`: auth/session adapter that resolves an `OARequestSession` for the route owner.
- `_output_invoice_collection_scope_keys_for_import_preview(...)` and `_output_invoice_collection_scope_keys_for_import_file_session(...)`: import fan-out scope providers for output invoice imports.
- `_invalidate_invoice_usage_collection_read_model_scopes(...)`: shared invoice-usage invalidation fan-out that can include `output_invoice_collection` when upstream scope changes affect the invoice-usage collection family.

## Classification

- Route ownership: accounted. All `/api/output-invoice-collections*` HTTP mapping lives in `OutputInvoiceCollectionApiRoutes`; static Guard prevents callback regression.
- Read-model fresh gate: accounted. Schema stale, source-version proof, fail-closed refreshing, all-rows aggregation and relation detail fail-closed handling live in `OutputInvoiceCollectionReadModelFreshGateService`.
- Business rules: accounted for this local `server.py` surface. Collection status, receipt lifecycle, red relation and lifecycle overlay remain in output collection services/route owner.
- Persistence/SQL details: accounted for this local surface. SQL table/repository logic remains outside `server.py`.
- Remaining production evidence: deferred. Real PostgreSQL/worker/App Status/high-row/browser closure still needs later controlled production validation and is not claimed here.

## Decision

Output collection local `server.py` support is accounted for after:

- route-owner read/export/status/history/detail collapse;
- mutation/receipt/red-relation route callback collapse;
- read-model fresh-gate service extraction;
- runtime/static/API Guard coverage.

No additional output collection `server.py` implementation slice is selected at this point.

## Next Boundary

`server-py:oa-pending-payment-route-owner-audit`

Reason: `server.py` still directly dispatches multiple `/api/oa-pending-payments*` callbacks even though `OaPendingPaymentApiRoutes` and `OaPendingPaymentReadModelService` exist. The next audit should split thin HTTP/session/body/error mapping from any residual business/read-model implementation and select the next bounded implementation slice.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_output_invoice_collection_read_export_routes_use_route_owner -v`
- `bash scripts/verify.sh docs`
- `git diff --check`
