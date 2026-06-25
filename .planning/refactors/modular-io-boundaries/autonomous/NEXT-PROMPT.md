# Next Prompt

Continue after `server-py:oa-pending-payment-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:oa-pending-payment-route-owner-audit`.
- Row363 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-oa-pending-payment-route-owner-audit-2026-06-25.md`.
- OA pending payment route callbacks in `server.py` are thin wrappers around `OaPendingPaymentApiRoutes`, `OaPendingPaymentReadModelService` and `OaPendingPaymentCommandService`.
- OA pending payment module/global closure and production PostgreSQL/OA/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:oa-pending-payment-route-owner-audit` is complete:

- audited direct `/api/oa-pending-payments*` dispatch and `_handle_api_oa_pending_payments*` callbacks;
- classified callbacks as auth/session, body parsing, write actor, JSON/error/status mapping only;
- selected full route callback collapse as the next bounded implementation slice.

## Next Boundary

`server-py:oa-pending-payment-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-oa-pending-payment-route-owner-audit-2026-06-25.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/oa-pending-payments/state-machine.md`
   - `docs/modules/oa-pending-payments/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around `/api/oa-pending-payments*` dispatch and callbacks
   - `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
   - `tests/test_oa_pending_payment_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before implementation-oriented changes if more context is needed.
4. Implement:
   - add `route(method, route_path, query, body, headers)` to `OaPendingPaymentApiRoutes`;
   - inject explicit ports for read-session resolution, write auth, JSON response, body loading and error response;
   - move rows/filter-options/detail/candidates/confirm-paid/auto-reconcile/link-bank HTTP mapping from `server.py` into route owner;
   - preserve repeated query params, read-model 202 refreshing status, structured `OaPendingPaymentError` responses and command-unavailable 503 mapping;
   - remove app-owned `_handle_api_oa_pending_payments*` callbacks.
5. Update tests/guards/docs/state and commit/push if verification passes.

## Stop Gates

- Do not change OA payment business rules, read-model freshness/source-version contracts, command-service semantics or frontend API shape.
- Do not run production validation or mutation.
- Do not claim OA pending payment module/global closure from this route-owner slice.
- Do not broaden into unrelated `server.py` domains.
