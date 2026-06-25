# Next Prompt

Continue after `server-py:input-invoice-usage-read-route-owner-facade-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-read-route-owner-facade-extraction`.
- Row349 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-read-route-owner-facade-extraction-2026-06-25.md`.
- `InputInvoiceUsageApiRoutes` now owns:
  - rows;
  - filter-options;
  - invoice detail;
  - bank transaction detail;
  - OA detail;
  - relation details;
  - payment-status-rules GET.
- `InputInvoiceUsageOaReverseApiRoutes` owns all OA reverse routes.
- `server.py` still owns export preview/download and payment-status-rules PUT.

## Next Boundary

`server-py:input-invoice-usage-export-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-read-route-owner-facade-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
   - `backend/src/fin_ops_platform/app/server.py` around export preview/download and export service helpers.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before selecting or editing any implementation boundary.
4. Audit export preview/download:
   - classify XLSX response bytes and headers;
   - classify export audit side effect;
   - decide whether to move export preview and download together into `InputInvoiceUsageApiRoutes`, or first introduce an explicit export file response type/port;
   - preserve refreshing payload behavior and row-limit errors.
5. Do not change export behavior in the audit.
6. Write analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change API response shape, file download headers, audit behavior or read-model freshness semantics.
- Do not touch payment-status-rules PUT in this boundary.
- Do not run production validation or perform production mutation.
