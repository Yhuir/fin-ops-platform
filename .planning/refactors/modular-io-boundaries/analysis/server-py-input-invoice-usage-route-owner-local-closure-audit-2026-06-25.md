# server-py:input-invoice-usage-route-owner-local-closure-audit

Status: `analysis-closed`

## Scope

This audit reviewed remaining `input_invoice_usage` surfaces in `server.py` after:

- OA reverse route ownership moved to `InputInvoiceUsageOaReverseApiRoutes`;
- rows/filter/detail/relation/payment GET moved to `InputInvoiceUsageApiRoutes`;
- export preview/download moved to `InputInvoiceUsageApiRoutes`;
- payment-status-rules PUT moved to `InputInvoiceUsageApiRoutes`.

The audit does not claim whole input usage module/global closure.

## Route Ownership Result

Route-owner support is locally accounted for:

- `server.py` dispatches `/api/input-invoice-usage*` through route owners.
- No `_handle_api_input_invoice_usage_*` route callback remains for the audited route set.
- Static Guard prevents rows/filter/detail/relation/payment/export callbacks from returning to `server.py`.

## Residual Surface Classification

| Surface | Classification | Notes |
| --- | --- | --- |
| `_input_invoice_usage_service(...)`, `_invoice_lifecycle_policy(...)`, `_input_invoice_usage_export_service(...)`, `_input_invoice_usage_routes(...)`, `_input_invoice_usage_oa_reverse_service(...)`, `_input_invoice_usage_oa_reverse_routes(...)` | dependency assembly | Acceptable in `Application` for now; constructors receive explicit services/ports rather than whole `Application`. |
| `_input_invoice_usage_payment_rules_provider(...)` | dependency assembly/settings provider port | Acceptable provider construction; payment rules business validation/persistence lives in service/provider. |
| `_target_oa_applicant_token_provider(...)`, `_input_invoice_usage_oa_draft_client_for_batch(...)` | external/OA platform port | Acceptable for route-owner local closure; real OA/browser/admin evidence remains production validation. |
| `_input_invoice_usage_mutation_actor(...)` | HTTP/session/platform mapping port | Acceptable explicit auth/mutation actor port for OA reverse route owner. |
| `_record_input_invoice_usage_oa_reverse_audit(...)`, `_record_input_invoice_usage_export_download(...)` | audit/platform port | Acceptable route-owner dependency ports. |
| `_input_invoice_usage_xlsx_response(...)`, `_input_invoice_usage_export_query_kwargs(...)`, `_input_invoice_usage_export_error_response(...)`, `_input_invoice_usage_payment_rules_error_response(...)`, `_input_invoice_usage_oa_reverse_error_response(...)`, `_input_invoice_usage_error_response(...)` | HTTP/response mapping port | Acceptable after route callback collapse; response shape remains guarded by API regressions. |
| `_invalidate_input_invoice_usage_oa_reverse_read_models(...)`, `_enqueue_input_invoice_usage_payment_rules_refreshes(...)`, `_enqueue_input_invoice_usage_read_model_refresh(...)`, `_invalidate_invoice_usage_collection_read_model_scopes(...)` | refresh producer port | Gateway-backed and locally acceptable as explicit ports, but broader shared extraction may be needed later. |
| `_input_invoice_usage_scope_keys_for_import_preview(...)`, `_input_invoice_usage_scope_keys_for_import_file_session(...)` | import scope adapter port | Acceptable thin adapter around shared invoice relation scope helper. |
| `_load_input_invoice_usage_export_page(...)`, `_input_invoice_usage_export_query_from_kwargs(...)` | implementation gap | Export service calls back into `Application` for row-page loading and fallback live query. This is module-specific read/query orchestration, not just HTTP mapping. |
| `_get_input_invoice_usage_all_rows_from_sql_read_model(...)`, `_get_input_invoice_usage_rows_from_sql_read_model(...)`, `_get_input_invoice_usage_relation_details_from_sql_read_model(...)`, `_input_invoice_usage_sql_payload_requires_schema_refresh(...)`, `_input_invoice_usage_expected_source_versions(...)` | implementation gap | These own SQL read-model fresh gate, source-version proof, stale/readiness payloads, schema checks and enqueue decisions. This is module-specific read-model freshness logic inside `Application`. |

## Selected Next Boundary

`server-py:input-invoice-usage-read-model-fresh-gate-service-extraction`

Extract a focused input usage read-model freshness/query adapter out of `Application` for:

- rows SQL read-model fresh gate;
- all-rows pagination/freshness aggregation for input usage;
- relation detail SQL read-model fresh gate;
- source-version provider wiring;
- schema-shape stale detection;
- export row-page loading through the same adapter.

The next slice should preserve current behavior and use explicit ports for:

- SQL read repository;
- query service fallback;
- enqueue refresh;
- expected source versions;
- JSON/refreshing payload construction only where still HTTP-specific.

## Stop Gates For Next Slice

- Do not change output invoice collection behavior while extracting input usage.
- Do not move shared invoice relation helpers unless needed for input usage and protected by output collection regressions.
- Do not weaken production fail-closed behavior when SQL repository is unavailable.
- Do not change export preview/download response shape or read-model refreshing semantics.
- Do not run production validation or mutation.

## Verification

Analysis-only slice. Evidence came from:

- CodeGraph context for input usage route owners and payment rules/provider surfaces;
- `rg` inventory of all `input_invoice_usage` references in `server.py`;
- source inspection of route factories, export ports, payment ports, OA reverse ports, SQL read-model fresh gates, source-version helpers and refresh producer helpers;
- existing static Guard coverage in `tests/test_platform_runtime_boundary_guards.py`.

No runtime code changed in this audit slice.
