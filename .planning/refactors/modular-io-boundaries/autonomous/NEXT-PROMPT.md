# Next Prompt

Continue after `server-py:input-invoice-usage-export-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-export-route-owner-audit`.
- Row350 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-export-route-owner-audit-2026-06-25.md`.
- `InputInvoiceUsageApiRoutes` owns input usage read HTTP mapping.
- `InputInvoiceUsageOaReverseApiRoutes` owns all OA reverse routes.
- `server.py` still owns export preview/download and payment-status-rules PUT.
- The next implementation should move only export preview/download into `InputInvoiceUsageApiRoutes`.

## Next Boundary

`server-py:input-invoice-usage-export-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-export-route-owner-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
   - `backend/src/fin_ops_platform/app/server.py` around export preview/download helpers.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing.
4. Implement export callback collapse:
   - extend `InputInvoiceUsageApiRoutes` for export preview/download;
   - inject explicit ports: `export_service`, `resolve_read_session`, `export_query_kwargs`, `export_error_response`, `record_export_download`, `xlsx_response`;
   - remove `_handle_api_input_invoice_usage_export_preview(...)` and `_handle_api_input_invoice_usage_export(...)` from `server.py`;
   - keep `_handle_api_input_invoice_usage_payment_status_rules_update(...)` in `server.py`.
5. Extend static Guard and run export preview/download, read route and OA reverse targeted API regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change API response shape, file download headers, audit behavior or read-model freshness semantics.
- Do not touch payment-status-rules PUT.
- Do not run production validation or perform production mutation.
