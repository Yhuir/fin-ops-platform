# server-py:input-invoice-usage-export-route-owner-audit

Status: `analysis-closed`

## Scope

This audit reviewed the remaining input-invoice usage export handlers in `Application`:

- `GET /api/input-invoice-usage/export-preview`
- `GET /api/input-invoice-usage/export`

`PUT /api/input-invoice-usage/payment-status-rules` is out of scope.

## Findings

- `InputInvoiceUsageExportService` already owns export preview row collection, row-limit validation, workbook generation and read-model refreshing payload behavior.
- `Application` still owns:
  - read-session check;
  - query-to-export kwargs mapping;
  - export service error response mapping;
  - export download audit record;
  - XLSX `Response` construction with content type and content-disposition headers.
- Export preview can move as ordinary JSON mapping.
- Export download can move if the route owner receives explicit ports for:
  - auth/read session resolution;
  - export query kwargs conversion;
  - export error mapping;
  - audit recording;
  - XLSX file response construction.
- The route owner must not import or construct `Application`.

## Selected Next Boundary

`server-py:input-invoice-usage-export-route-callback-collapse`

Extend `InputInvoiceUsageApiRoutes` to own:

- `GET /api/input-invoice-usage/export-preview`
- `GET /api/input-invoice-usage/export`

Use explicit ports:

- `export_service`
- `resolve_read_session`
- `export_query_kwargs`
- `export_error_response`
- `record_export_download`
- `xlsx_response`

Then remove `_handle_api_input_invoice_usage_export_preview(...)` and `_handle_api_input_invoice_usage_export(...)` from `server.py`.

## Required Guard/Test Evidence

- Extend static Guard to prove export preview/download are route-owned.
- Keep `PUT /api/input-invoice-usage/payment-status-rules` in `Application` until its own write-boundary audit.
- Re-run export preview/download and refreshing API regressions, read route-owner Guard, compile and docs checks.

## Stop Gates

- Do not change API response shape, file download headers, audit behavior or read-model freshness semantics.
- Do not touch payment-status-rules PUT.
- Do not run production validation.
- Do not perform production mutation.

## Verification

Analysis-only slice. Evidence was collected from CodeGraph and source inspection of:

- `Application._handle_api_input_invoice_usage_export_preview(...)`
- `Application._handle_api_input_invoice_usage_export(...)`
- `InputInvoiceUsageExportService`
- export API regressions in `tests/test_input_invoice_usage_api.py`

No runtime code changed in this audit slice.
