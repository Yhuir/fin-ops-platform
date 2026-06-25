# server-py:oa-pending-payment-route-callback-collapse

Status: `local-implementation-closed`

Date: 2026-06-25

## Boundary

Move `/api/oa-pending-payments*` HTTP mapping out of `Application` and into `OaPendingPaymentApiRoutes`.

This is a local implementation boundary only. It does not claim OA pending payment module/global closure or production PostgreSQL/OA/worker/App Status/browser closure.

## Implementation

- Added `OaPendingPaymentApiRoutes.route(...)`.
- Injected explicit platform ports into the route owner:
  - read-session resolver;
  - write-auth context;
  - JSON response;
  - JSON body loader;
  - structured `OaPendingPaymentError` response.
- Added `configure_platform_ports(...)` so `Application` can safely configure route-owner ports even when tests inject a prebuilt route owner.
- Replaced direct `/api/oa-pending-payments*` dispatch in `server.py` with `_oa_pending_payment_routes().route(...)`.
- Removed app-owned `_handle_api_oa_pending_payments*` callbacks and `_oa_pending_payment_sql_payload_status(...)`.
- Updated API tests that previously called app-owned callbacks so they validate route/read-model service contracts without depending on removed callback names.
- Added runtime boundary Guard coverage to prevent OA pending payment callbacks from returning to `server.py`.

## Preserved Behavior

- Rows/filter-options/detail routes still enforce read session authorization.
- Command routes still parse JSON body, resolve write actor and return structured command errors.
- `OaPendingPaymentError` response shape is unchanged.
- Command-service unavailable still maps to `503` with `oa_pending_payment_command_unavailable`.
- Read-model refreshing detail/rows/filter payloads still map to `202`.
- Repeated query params such as `oa_row_ids` remain preserved through the route owner.
- Business behavior remains in `OaPendingPaymentReadModelService`, `OaPendingPaymentCommandService` and `OaPendingPaymentQueryService`.

## Tests And Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_oa_pending_payments.py backend/src/fin_ops_platform/app/server.py tests/test_oa_pending_payment_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_pending_payment_routes_use_route_owner -v`

## Docs Impact

Docs applicable. Updated module implementation notes and autonomous state files. Long-term product/API semantics did not change.

## Next Boundary

`server-py:oa-pending-payment-route-owner-local-closure-audit`

Audit remaining OA pending payment `Application` surfaces after route callback collapse. Classify remaining service factories, read-model service factory, source-version provider, refresh enqueue, payment projection/source adapter and relation repository helpers as acceptable composition/provider ports or select the next residual implementation gap.
