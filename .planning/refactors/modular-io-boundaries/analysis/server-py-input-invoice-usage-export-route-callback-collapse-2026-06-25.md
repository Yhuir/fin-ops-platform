# server-py:input-invoice-usage-export-route-callback-collapse

Status: `local-implementation-closed`

## Scope

This slice collapsed the two input-invoice usage export HTTP callbacks out of `Application`:

- `GET /api/input-invoice-usage/export-preview`
- `GET /api/input-invoice-usage/export`

`PUT /api/input-invoice-usage/payment-status-rules` stays in `Application` for its own write-boundary audit.

## Implementation

- Extended `InputInvoiceUsageApiRoutes` to own export preview/download route matching and HTTP response mapping.
- Injected explicit ports from `Application`:
  - `export_service`;
  - `resolve_read_session`;
  - `export_query_kwargs`;
  - `export_error_response`;
  - `record_export_download`;
  - `xlsx_response`.
- Removed `_handle_api_input_invoice_usage_export_preview(...)` and `_handle_api_input_invoice_usage_export(...)` from `server.py`.
- Kept export auth, read-model refreshing semantics, export error mapping, audit metadata and XLSX response headers unchanged through the injected ports.
- Updated the route-owner static guard so export preview/download cannot regress back into `server.py`.

## Boundary Evidence

- `InputInvoiceUsageApiRoutes` now owns input usage rows/filter/detail/relation/payment-rules GET plus export preview/download HTTP mapping.
- `server.py` assembles route-owner dependencies and retains platform ports for auth/session, JSON/XLSX responses, audit and export query normalization.
- `Application` no longer owns the two export route handlers.
- Payment rules PUT remains intentionally out of scope because it is a settings write plus refresh fan-out boundary.

## Tests And Guards

- Static route-owner guard now requires:
  - explicit export/auth/audit/XLSX ports in `_input_invoice_usage_routes(...)`;
  - export preview/download route markers in `InputInvoiceUsageApiRoutes`;
  - removed export handlers absent from `server.py`;
  - payment-status-rules PUT retained in `server.py`.
- API regressions cover export preview/download filter behavior and refreshing payload behavior.
- Existing read route and OA reverse regressions cover dispatch fallthrough around the widened `/api/input-invoice-usage` route owner.

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_input_invoice_usage.py backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_input_invoice_usage_api.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_usage_read_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_oa_reverse_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_export_preview_and_download_use_current_input_invoice_usage_filters tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_export_returns_refreshing_when_sql_read_model_is_not_fresh tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_rows_route_returns_aggregated_rows_with_filters_sort_and_pagination tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_filter_options_payment_rules_details_and_relation_routes tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_preview_batch_and_missing_client_draft_routes_are_formal_workflow -v
```

## Docs Impact

- Module implementation notes are updated.
- Long-term API/product docs are unchanged because response shape, status codes and XLSX headers are unchanged.
- State-machine definitions are unchanged; this is an ownership migration slice using existing statuses.

## Next Boundary

`server-py:input-invoice-usage-payment-rules-write-boundary-audit`

Audit `PUT /api/input-invoice-usage/payment-status-rules` before moving it. That callback is a settings write and read-model refresh fan-out path, so the next slice must classify write ownership, settings validation, actor/permission behavior, audit/freshness impact and whether to extract a service/write route owner or keep an explicit compat wrapper.
