# server-py:input-invoice-usage-payment-rules-route-callback-collapse

Status: `local-implementation-closed`

## Scope

This slice moved `PUT /api/input-invoice-usage/payment-status-rules` HTTP mapping out of `Application` and into `InputInvoiceUsageApiRoutes`.

## Implementation

- Extended `InputInvoiceUsageApiRoutes.route(...)` to receive `body` and handle `PUT /api/input-invoice-usage/payment-status-rules`.
- Added `InputInvoiceUsageApiRoutes.update_payment_status_rules(...)` for:
  - read-session resolution;
  - mutation permission check;
  - JSON body parsing;
  - actor fallback;
  - settings service update invocation;
  - payment-rules validation error mapping;
  - HTTP JSON response serialization.
- Injected explicit ports from `Application`:
  - `app_settings_service`;
  - `load_json_body`;
  - `payment_rules_refreshes`;
  - `payment_rules_error_response`.
- Removed `_handle_api_input_invoice_usage_payment_status_rules_update(...)` from `server.py`.
- Kept `_enqueue_input_invoice_usage_payment_rules_refreshes(...)` in `Application` as an explicit read-model refresh producer port for this slice. It still enqueues `input_invoice_usage:all` and `invoice_lifecycle:all`.

## Boundary Evidence

- The route owner now owns all `/api/input-invoice-usage` non-OA-reverse HTTP mapping currently in scope:
  - rows/filter/detail/relation/payment rules GET;
  - export preview/download;
  - payment rules PUT.
- `server.py` still assembles dependencies and owns platform/read-model producer ports, but no longer owns the payment rules PUT callback.
- Settings validation, persistence, idempotency, version conflict and audit remain in the settings service/provider.
- Payment rules refresh fan-out remains gateway-backed and outside the route owner.

## Tests And Guards

- Static Guard now requires explicit settings/body/error/refresh ports and prevents `_handle_api_input_invoice_usage_payment_status_rules_update(...)` from returning to `server.py`.
- Payment rules save regression now exercises `app.handle_request("PUT", "/api/input-invoice-usage/payment-status-rules", ...)` instead of the removed private handler.
- Permission regression for read-only export users still proves payment rules PUT is forbidden.

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_input_invoice_usage.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_input_invoice_usage_payment_rules.py tests/test_auth_guard.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_usage_read_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_payment_rules.InputInvoiceUsagePaymentRulesTests.test_put_rules_handler_saves_and_enqueues_refresh tests.test_input_invoice_usage_payment_rules.InputInvoiceUsagePaymentRulesTests.test_rules_update_persists_audits_and_returns_invalidation_event tests.test_input_invoice_usage_payment_rules.InputInvoiceUsagePaymentRulesTests.test_rules_update_validates_version_idempotency_and_supported_constraints -v
PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard.AuthGuardTests.test_readonly_export_user_can_export_but_cannot_mutate_or_admin -v
```

## Docs Impact

- Module implementation notes are updated.
- Long-term API/product docs are unchanged because route path, response payload, validation codes, permission behavior, audit and refresh fan-out are unchanged.
- State-machine definitions are unchanged; this is an ownership migration slice.

## Next Boundary

`server-py:input-invoice-usage-route-owner-local-closure-audit`

Audit the remaining input-usage surfaces in `server.py` after rows/filter/detail/export/payment routes moved into `InputInvoiceUsageApiRoutes`. Classify each residual helper as dependency assembly, HTTP/platform mapping, read-model/freshness port, refresh producer port, compat-only wrapper or implementation gap. Do not claim whole module/global closure from route-owner support alone.
