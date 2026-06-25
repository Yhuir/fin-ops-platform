# Next Prompt

Continue after `server-py:input-invoice-usage-payment-rules-write-boundary-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-payment-rules-write-boundary-audit`.
- Row352 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-payment-rules-write-boundary-audit-2026-06-25.md`.
- `InputInvoiceUsageApiRoutes` owns input usage read/export HTTP mapping.
- `server.py` still owns `PUT /api/input-invoice-usage/payment-status-rules` as a thin HTTP wrapper.

## Previous Prompt Completion

`server-py:input-invoice-usage-payment-rules-write-boundary-audit` is complete:

- settings validation, persistence, audit, version conflict and idempotency conflict live in the settings service/provider;
- `Application` owns session/body/error mapping and actor fallback;
- refresh fan-out is already isolated in `_enqueue_input_invoice_usage_payment_rules_refreshes(...)`;
- the next safe local implementation is route callback collapse with explicit ports.

## Next Boundary

`server-py:input-invoice-usage-payment-rules-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-payment-rules-write-boundary-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
   - `backend/src/fin_ops_platform/app/server.py` around `_handle_api_input_invoice_usage_payment_status_rules_update(...)`
   - `backend/src/fin_ops_platform/services/app_settings_service.py`
   - `tests/test_input_invoice_usage_payment_rules.py`
   - `tests/test_auth_guard.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing.
4. Implement callback collapse narrowly:
   - extend `InputInvoiceUsageApiRoutes.route(...)` to handle `PUT /api/input-invoice-usage/payment-status-rules`;
   - inject explicit ports for settings service, body parsing, refresh fan-out and payment-rules error mapping;
   - remove `_handle_api_input_invoice_usage_payment_status_rules_update(...)` from `server.py`;
   - keep `_enqueue_input_invoice_usage_payment_rules_refreshes(...)` in `Application` as an explicit refresh producer port for this slice.
5. Update tests:
   - static Guard must prove the PUT callback is route-owned and removed from `server.py`;
   - payment rules API test must exercise the public route path, not the removed private handler;
   - keep permission denial and conflict/validation behavior covered.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change settings service validation, persistence, audit metadata, idempotency semantics or response payload shape.
- Do not move read-model enqueue/gateway behavior into the route owner.
- Do not weaken mutation permission checks.
- Do not run production validation or perform production mutation.
- Do not claim input usage module/global closure from this route-owner slice alone.
