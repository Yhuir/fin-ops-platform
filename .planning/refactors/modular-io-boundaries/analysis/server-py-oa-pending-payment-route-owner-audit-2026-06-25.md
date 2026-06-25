# server-py:oa-pending-payment-route-owner-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining `/api/oa-pending-payments*` route ownership in `Application` and select the next bounded local implementation slice.

This is an analysis boundary only. It does not change runtime code and does not claim OA pending payment module/global closure or production PostgreSQL/OA/worker/App Status/browser closure.

## Evidence Reviewed

- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/oa-pending-payments/state-machine.md`
- `docs/modules/oa-pending-payments/tests.md`
- CodeGraph context for `OaPendingPaymentApiRoutes`, `OaPendingPaymentReadModelService`, `OaPendingPaymentCommandService` and `Application` callbacks.
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py`
- `tests/test_oa_pending_payment_api.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Current Shape

`OaPendingPaymentApiRoutes` already owns module-level route methods for:

- rows;
- filter options;
- OA/bank/invoice detail;
- relation details;
- bank transaction candidates;
- confirm paid;
- auto reconcile bank transactions;
- link bank transactions.

`OaPendingPaymentReadModelService` owns read-model freshness/source-version/detail unavailable behavior. `OaPendingPaymentCommandService` owns automatic writeback, bank link and payment command behavior.

`server.py` still owns direct dispatch plus thin callbacks:

- `_handle_api_oa_pending_payments_rows(...)`
- `_handle_api_oa_pending_payments_filter_options(...)`
- `_handle_api_oa_pending_payments_oa_detail(...)`
- `_handle_api_oa_pending_payments_bank_transaction_detail(...)`
- `_handle_api_oa_pending_payments_invoice_detail(...)`
- `_handle_api_oa_pending_payments_relation_details(...)`
- `_handle_api_oa_pending_payments_bank_transaction_candidates(...)`
- `_handle_api_oa_pending_payments_confirm_paid(...)`
- `_handle_api_oa_pending_payments_auto_reconcile_bank_transactions(...)`
- `_handle_api_oa_pending_payments_link_bank_transactions(...)`

## Classification

- Read routes are thin auth/error/JSON wrappers around `OaPendingPaymentApiRoutes` and `OaPendingPaymentReadModelService`.
- Detail route status mapping is a generic SQL payload status adapter: `refreshing` maps to 202; fresh maps to 200.
- Candidate route is a read-session-protected HTTP wrapper around command-service candidate lookup.
- Command routes are body parsing, write auth actor extraction, service error mapping and JSON response wrappers around command-service methods.
- Business rules remain service-owned: payment status, flow_id admission, active/pending relations, writeback, bank link, auto reconcile and source-version/freshness contracts are not implemented in these callbacks.

## Decision

The next safe implementation slice is a route callback collapse:

`server-py:oa-pending-payment-route-callback-collapse`

Scope:

- Add `route(method, route_path, query, body, headers)` to `OaPendingPaymentApiRoutes`.
- Inject explicit platform ports for read-session resolution, write auth, JSON response, body loading and error response.
- Move all `/api/oa-pending-payments*` HTTP mapping from `server.py` into the route owner.
- Remove the app-owned `_handle_api_oa_pending_payments*` callbacks after route owner handles the same contracts.
- Preserve repeated query params such as `oa_row_ids`.
- Preserve read-model `202` refreshing status, structured `OaPendingPaymentError` responses and command-service unavailable responses.

## Verification Plan For Next Slice

- Add/update API regressions in `tests/test_oa_pending_payment_api.py` for route-owner dispatch, candidate repeated query params, read auth denial, write actor propagation and command unavailable mapping.
- Add/update static Guard in `tests/test_platform_runtime_boundary_guards.py` to prevent OA pending payment callbacks returning to `server.py`.
- Run:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api -v`
  - targeted platform runtime boundary Guard
  - `bash scripts/verify.sh docs`
  - `git diff --check`

## Next Boundary

`server-py:oa-pending-payment-route-callback-collapse`
