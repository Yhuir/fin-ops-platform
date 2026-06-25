# Next Prompt

Continue after `server-py:input-invoice-usage-oa-reverse-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-oa-reverse-route-owner-local-closure-audit`.
- Row347 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-local-closure-audit-2026-06-25.md`.
- OA reverse route-owner local support is accounted for:
  - all `/api/input-invoice-usage/oa-reverse*` HTTP mapping lives in `InputInvoiceUsageOaReverseApiRoutes`;
  - no `_handle_api_input_invoice_usage_oa_reverse_*` route handler remains in `server.py`;
  - remaining OA reverse `Application` methods are explicit dependency/platform/helper ports.
- Whole input-invoice-usage and global modular closure are not claimed.

## Next Boundary

`server-py:input-invoice-usage-core-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/input-invoice-usage/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `/api/input-invoice-usage/rows`;
     - `/api/input-invoice-usage/filter-options`;
     - `/api/input-invoice-usage/export-preview`;
     - `/api/input-invoice-usage/export`;
     - `/api/input-invoice-usage/payment-status-rules`;
     - invoice/bank/OA detail routes;
     - relation-details;
     - SQL read model fresh-gate helpers.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before selecting or editing any implementation boundary.
4. Audit remaining non-OA-reverse input-invoice usage routes and classify:
   - which handlers are pure HTTP mapping and can move into a route owner;
   - which helpers are read model fresh-gate/platform ports and should remain explicit dependencies;
   - whether export download response bytes require a special route return type or app wrapper;
   - whether payment-status rules should move together or become a smaller application-service boundary first.
5. Do not change rows/filter/export/read-model fresh gates in the audit.
6. Write an analysis file, update state/docs, and commit/push if verification passes.

## Stop Gates

- Do not change API response shape, file download headers, permission behavior or read-model freshness semantics.
- Do not touch production validation.
- Do not perform production mutation.
