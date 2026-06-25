# Next Prompt

Continue after `server-py:input-invoice-usage-core-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-core-route-owner-audit`.
- Row348 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-core-route-owner-audit-2026-06-25.md`.
- OA reverse route-owner local support is already accounted for.
- The selected next implementation slice must move only read HTTP mapping into a route owner:
  - rows;
  - filter-options;
  - invoice detail;
  - bank transaction detail;
  - OA detail;
  - relation details;
  - payment-status-rules GET.
- Keep export preview/download and payment-status-rules PUT in `Application` for later slices.
- Do not rewrite SQL/read-model fresh-gate helpers.

## Next Boundary

`server-py:input-invoice-usage-read-route-owner-facade-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-core-route-owner-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around the selected handlers and fresh-gate helpers.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing.
4. Implement:
   - add `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`;
   - define `InputInvoiceUsageApiRoutes` with explicit ports:
     - `query_service`;
     - `rows_from_sql_read_model`;
     - `all_rows_from_sql_read_model`;
     - `relation_details_from_sql_read_model`;
     - `json_response`;
     - `input_usage_error_response`;
   - delegate selected read routes from `server.py` into the route owner;
   - remove selected legacy handlers from `server.py`;
   - leave export preview/download and payment-status-rules PUT in `Application`.
5. Add/extend static Guard and run targeted API regressions for rows/filter/detail/relation-details/payment GET.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change API response shape, file download headers, permission behavior or read-model freshness semantics.
- Do not touch export preview/download in this slice.
- Do not touch payment-status-rules PUT in this slice.
- Do not run production validation or perform production mutation.
