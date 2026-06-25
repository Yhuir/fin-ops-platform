# server-py:input-invoice-usage-payment-rules-write-boundary-audit

Status: `analysis-closed`

## Scope

This audit reviewed:

- `PUT /api/input-invoice-usage/payment-status-rules`
- `Application._handle_api_input_invoice_usage_payment_status_rules_update(...)`
- `Application._enqueue_input_invoice_usage_payment_rules_refreshes(...)`
- `AppSettingsService.update_input_invoice_usage_payment_status_rules(...)`
- `AppSettingsInputInvoiceUsagePaymentRulesProvider.update_payment_status_rules(...)`

`GET /api/input-invoice-usage/payment-status-rules` is already route-owned by `InputInvoiceUsageApiRoutes`.

## Findings

- The write-side business contract already lives outside `Application`:
  - request normalization, version conflict, idempotency conflict and rule validation are in `AppSettingsInputInvoiceUsagePaymentRulesProvider`;
  - persistence goes through the app settings state store;
  - audit record `input_invoice_usage_payment_status_rules_updated` is produced by the payment rules provider via the settings service;
  - response payload shape is the public payment rules payload returned by the settings service.
- `Application._handle_api_input_invoice_usage_payment_status_rules_update(...)` still owns only HTTP/platform mapping:
  - read-session resolution;
  - mutation permission check;
  - JSON body parsing;
  - actor fallback;
  - `AppSettingsValidationError` to HTTP status mapping;
  - final JSON response serialization.
- The refresh side effect is already isolated in a narrow app-owned port:
  - `_enqueue_input_invoice_usage_payment_rules_refreshes(...)` enqueues `input_invoice_usage:all`;
  - it also fans out `invoice_lifecycle:all` through `_enqueue_generic_read_model_refreshes(...)`;
  - prior invoice-lifecycle audit classified this fan-out as legitimate and gateway-backed.
- Existing tests cover:
  - direct handler save plus `input_invoice_usage` / `invoice_lifecycle` refresh enqueue;
  - settings service persistence, audit, validation, version conflict and idempotency conflict;
  - read-only user permission denial for this PUT route.

## Selected Next Boundary

`server-py:input-invoice-usage-payment-rules-route-callback-collapse`

Move the payment-status-rules PUT HTTP mapping into `InputInvoiceUsageApiRoutes` using explicit ports:

- `resolve_read_session`;
- `load_json_body`;
- `app_settings_service`;
- `payment_rules_refreshes`;
- `json_response`;
- `payment_rules_error_response` or equivalent error mapper.

Keep the refresh fan-out helper in `Application` as an explicit platform/read-model producer port for the first implementation slice. Do not move gateway/queue behavior into the route owner.

## Required Guard/Test Evidence

- Extend the input usage route-owner static Guard so:
  - `InputInvoiceUsageApiRoutes` owns PUT `/api/input-invoice-usage/payment-status-rules`;
  - `_handle_api_input_invoice_usage_payment_status_rules_update(...)` is absent from `server.py`;
  - the factory injects explicit settings/body/error/refresh ports.
- Update direct handler tests to call `app.handle_request(...)` or route-owner path rather than the removed private handler.
- Preserve existing API contract:
  - HTTP 200 on success;
  - HTTP 403 for read-only users;
  - HTTP 409 for version/idempotency conflicts;
  - HTTP 400 for other validation errors;
  - unchanged response payload and refresh fan-out.

## Stop Gates

- Do not change settings service validation, persistence, audit metadata or idempotency semantics.
- Do not move read-model enqueue/gateway behavior into the route owner.
- Do not weaken the permission check.
- Do not run production validation or mutation.

## Verification

Analysis-only slice. Evidence came from CodeGraph and source inspection of:

- `Application._handle_api_input_invoice_usage_payment_status_rules_update(...)`;
- `Application._enqueue_input_invoice_usage_payment_rules_refreshes(...)`;
- `AppSettingsService.update_input_invoice_usage_payment_status_rules(...)`;
- `AppSettingsInputInvoiceUsagePaymentRulesProvider.update_payment_status_rules(...)`;
- `tests/test_input_invoice_usage_payment_rules.py`;
- `tests/test_auth_guard.py`;
- `tests/test_platform_runtime_boundary_guards.py`.

No runtime code changed in this audit slice.
