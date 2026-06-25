# server-py:input-invoice-usage-post-fresh-gate-local-closure-audit

Status: `analysis-closed`

Date: 2026-06-25

## Scope

Audit remaining input invoice usage `Application` ownership after:

- input usage OA reverse route-owner extraction and callback collapse;
- core input usage route-owner facade extraction;
- export route callback collapse;
- payment-status-rules write callback collapse;
- read-model fresh gate service extraction.

This is a local `server.py` boundary audit. It does not claim full module closure or production evidence closure.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
- `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_fresh_gate_service.py`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/output-invoice-collections/README.md`
- `tests/test_platform_runtime_boundary_guards.py`
- Prior input usage analysis files:
  - `server-py-input-invoice-usage-route-owner-local-closure-audit-2026-06-25.md`
  - `server-py-input-invoice-usage-read-model-fresh-gate-service-extraction-2026-06-25.md`

CodeGraph context was used before the audit to inspect input usage route/service/fresh-gate surfaces.

## Remaining Input Usage `Application` Surface

| Surface | Classification | Evidence |
| --- | --- | --- |
| `_input_invoice_usage_service(...)`, `_input_invoice_usage_routes(...)`, `_input_invoice_usage_oa_reverse_service(...)`, `_input_invoice_usage_oa_reverse_routes(...)`, `_input_invoice_usage_export_service(...)`, `_input_invoice_usage_read_model_fresh_gate(...)` | dependency assembly | These construct services/routes with explicit dependencies and cache instances; they do not own route business behavior or fresh-gate decisions. |
| `_get_input_invoice_usage_rows_from_sql_read_model(...)`, `_get_input_invoice_usage_all_rows_from_sql_read_model(...)`, `_get_input_invoice_usage_relation_details_from_sql_read_model(...)` | thin compatibility/provider delegates | Each now delegates to `InputInvoiceUsageReadModelFreshGateService`; the previous app-owned schema/status/source-version/all-rows/detail implementation was removed. |
| `_input_invoice_usage_expected_source_versions(...)` | source-version provider port | Prior read-model local closure already classified this as an acceptable provider. After Row355, it is injected into the fresh-gate service and no longer performs HTTP mapping or freshness response assembly. |
| `_enqueue_input_invoice_usage_read_model_refresh(...)`, `_enqueue_input_invoice_usage_payment_rules_refreshes(...)`, `_invalidate_input_invoice_usage_oa_reverse_read_models(...)`, `_invalidate_invoice_usage_collection_read_model_scopes(...)` | refresh/invalidation ports | These delegate to `ReadModelRefreshGateway` or shared invalidation. They do not direct-SQL write dirty scopes, outbox, readiness, cache or App Status. |
| `_input_invoice_usage_scope_keys_for_import_preview(...)`, `_input_invoice_usage_scope_keys_for_import_file_session(...)` | import scope adapter ports | Thin adapters over shared invoice relation import scope helpers; no read-model rebuild or SQL write ownership. |
| `_record_input_invoice_usage_export_download(...)`, `_input_invoice_usage_xlsx_response(...)`, `_input_invoice_usage_export_query_kwargs(...)`, `_input_invoice_usage_export_error_response(...)`, `_input_invoice_usage_payment_rules_error_response(...)`, `_input_invoice_usage_oa_reverse_error_response(...)`, `_input_invoice_usage_error_response(...)`, `_input_invoice_usage_mutation_actor(...)`, `_input_invoice_usage_oa_draft_client_for_batch(...)` | HTTP/platform/audit adapters | These are app-layer response, session, audit and external-client adapter ports consumed by route owners. They are not business state machines or read-model projection owners. |

## Findings

- No `_handle_api_input_invoice_usage*` callback remains in `server.py`.
- No input usage app-owned SQL payload schema helper remains.
- No input usage app-owned export row-page loader remains.
- No input usage app-owned fresh/stale/source-version response assembly remains.
- Remaining input usage methods in `Application` are explicit dependency, platform, refresh, source-version or compatibility provider ports.
- Input usage local `server.py` support is accounted for, but full module/global closure is not claimed because real PostgreSQL/worker/App Status/high-row/browser evidence remains final validation evidence.

## Next Boundary Selection

Next selected boundary: `server-py:output-invoice-collection-route-owner-audit`.

Rationale:

- `OutputInvoiceCollectionApiRoutes` already exists, but `Application` still owns many `_handle_api_output_invoice_collections*` callbacks and direct route dispatch branches.
- Output collection is adjacent to input usage in the shared invoice-usage-collection worker/read-model family and still has broad `server.py` route callback surface.
- A route-owner audit is safer than immediate implementation because output collection includes rows/filter/export, lifecycle writes, reminders, red invoice relations, receipts and receipt settings.

## Stop Gates For Next Boundary

- Do not change output collection behavior in the audit.
- Do not weaken output collection freshness/source-version/schema/fail-closed semantics.
- Do not claim output collection module closure from route-owner accounting alone.
- Do not run production validation or mutation while local implementation gaps remain.
