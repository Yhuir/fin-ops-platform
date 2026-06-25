# server-py:input-invoice-usage-core-route-owner-audit

Status: `analysis-closed`

## Scope

This audit reviewed the remaining non-OA-reverse input-invoice usage route handlers in `Application`:

- `GET /api/input-invoice-usage/rows`
- `GET /api/input-invoice-usage/filter-options`
- `GET /api/input-invoice-usage/export-preview`
- `GET /api/input-invoice-usage/export`
- `GET /api/input-invoice-usage/payment-status-rules`
- `PUT /api/input-invoice-usage/payment-status-rules`
- `GET /api/input-invoice-usage/invoices/{invoice_id}/detail`
- `GET /api/input-invoice-usage/bank-transactions/{bank_transaction_id}/detail`
- `GET /api/input-invoice-usage/oa/{oa_id}/detail`
- `GET /api/input-invoice-usage/rows/{row_id}/relation-details`

OA reverse routes are already locally accounted for and out of scope.

## Findings

- Rows and filter-options handlers still live in `server.py`, but they are mostly HTTP mapping around existing read model fresh-gate helpers:
  - `_get_input_invoice_usage_rows_from_sql_read_model(...)`
  - `_get_input_invoice_usage_all_rows_from_sql_read_model(...)`
  - `_input_invoice_usage_service()`
  - `_input_invoice_usage_error_response(...)`
- Detail handlers for invoice, bank transaction and OA are pure query-service HTTP wrappers.
- Relation detail already delegates the fresh/stale/source-version logic to `InputInvoiceUsageReadModelDetailService` when SQL read model detail is available, but `Application` still owns the HTTP wrapper and missing-repository fail-closed adapter.
- `GET /payment-status-rules` is a pure query-service wrapper.
- Export preview/download should not be moved in the first implementation slice because download returns XLSX bytes with content-disposition headers and records export audit. It deserves a dedicated export route boundary or return type.
- `PUT /payment-status-rules` should not move in the first implementation slice because it is a settings write path with mutation permission, version/idempotency errors and read model refresh fan-out to `input_invoice_usage` plus `invoice_lifecycle`.
- Read model fresh gates must not be rewritten or weakened. A route owner can receive the current fresh-gate helpers as explicit ports for the first read facade slice.

## Selected Next Boundary

`server-py:input-invoice-usage-read-route-owner-facade-extraction`

Move only these read HTTP mappings into a new `InputInvoiceUsageApiRoutes`:

- rows;
- filter-options;
- invoice detail;
- bank transaction detail;
- OA detail;
- relation details;
- payment-status-rules GET.

Keep these out of the first slice:

- export preview/download;
- payment-status-rules PUT;
- SQL fresh-gate helper implementations;
- read model enqueue/source-version helpers.

The route owner should use explicit dependencies and ports, not `Application`:

- `query_service`;
- `rows_from_sql_read_model`;
- `all_rows_from_sql_read_model`;
- `relation_details_from_sql_read_model`;
- `json_response`;
- `input_usage_error_response`.

## Required Guard/Test Evidence

- Add `routes_input_invoice_usage.py` to route-owner inventory.
- Add a static Guard proving the selected read handlers are removed from `server.py`, the route owner exists, and export/PUT handlers remain explicitly out of scope.
- Run targeted API regressions for rows/filter-options/detail/relation-details/payment rules plus compile checks.

## Stop Gates

- Do not change API response shape, file download headers, permission behavior or read-model freshness semantics.
- Do not touch export download or payment rules PUT in this first read route-owner slice.
- Do not run production validation.
- Do not perform production mutation.

## Verification

Analysis-only slice. Evidence was collected from:

- CodeGraph context for the remaining input usage route ownership;
- source inspection of `server.py` rows/filter/export/detail/payment handlers and SQL fresh-gate helpers;
- source inspection of `InputInvoiceUsageExportService`, `InputInvoiceUsageReadModelDetailService` and `InputInvoiceUsageQueryService`;
- existing module docs/tests inventory.

No runtime code changed in this audit slice.
