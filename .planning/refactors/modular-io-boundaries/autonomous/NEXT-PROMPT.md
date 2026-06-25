# Next Prompt

Continue after `server-py:input-invoice-usage-export-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-export-route-callback-collapse`.
- Row351 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-export-route-callback-collapse-2026-06-25.md`.
- `InputInvoiceUsageApiRoutes` now owns rows/filter/detail/relation/payment-rules GET plus export preview/download HTTP mapping.
- `server.py` no longer owns `_handle_api_input_invoice_usage_export_preview(...)` or `_handle_api_input_invoice_usage_export(...)`.
- `server.py` still owns `PUT /api/input-invoice-usage/payment-status-rules`.

## Previous Prompt Completion

`server-py:input-invoice-usage-export-route-callback-collapse` is complete for local implementation:

- export preview/download route callbacks were moved into `InputInvoiceUsageApiRoutes`;
- explicit export/auth/audit/XLSX ports are injected from `Application`;
- static Guard and targeted API regressions passed;
- production validation was not run and remains final validation only.

## Next Boundary

`server-py:input-invoice-usage-payment-rules-write-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-export-route-callback-collapse-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
   - `backend/src/fin_ops_platform/app/server.py` around `_handle_api_input_invoice_usage_payment_status_rules_update(...)`
   - settings service code owning `update_input_invoice_usage_payment_status_rules(...)`
   - read-model refresh fan-out helpers used after payment rules save
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit the payment-status-rules PUT boundary before moving code:
   - request body and validation ownership;
   - read-session/auth/mutation permission behavior;
   - actor fallback and audit behavior;
   - settings service ownership;
   - read-model refresh fan-out and persistence side effects;
   - API response/error shape;
   - whether the right next slice is route-owner callback collapse, service extraction, or retained compat wrapper with explicit deletion conditions.
5. Write the analysis file and update state/docs.
6. If the audit proves a safe narrow implementation slice, generate and execute that next slice immediately.

## Stop Gates

- Do not move payment rules PUT in the same step unless the audit proves the callback is already thin enough and all side effects are explicit ports.
- Do not change payment rules API response shape, validation messages, permission behavior, audit behavior or read-model refresh semantics.
- Do not run production validation or perform production mutation.
- Do not claim input usage module/global closure from Row351 or Row352 alone.
