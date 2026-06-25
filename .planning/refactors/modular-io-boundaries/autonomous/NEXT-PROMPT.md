# Next Prompt

Continue after `server-py:oa-pending-payment-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:oa-pending-payment-route-callback-collapse`.
- Row364 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-oa-pending-payment-route-callback-collapse-2026-06-25.md`.
- `/api/oa-pending-payments*` HTTP mapping now lives in `OaPendingPaymentApiRoutes.route(...)`.
- OA pending payment module/global closure and production PostgreSQL/OA/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:oa-pending-payment-route-callback-collapse` is complete:

- route owner handles rows/filter-options/detail/candidates/confirm-paid/auto-reconcile/link-bank HTTP dispatch;
- explicit ports cover read session, write auth, body loading, JSON response and structured `OaPendingPaymentError` mapping;
- app-owned `_handle_api_oa_pending_payments*` callbacks and `_oa_pending_payment_sql_payload_status(...)` were removed;
- API regressions and runtime boundary Guard pass.

## Next Boundary

`server-py:oa-pending-payment-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-oa-pending-payment-route-callback-collapse-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-oa-pending-payment-route-owner-audit-2026-06-25.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/oa-pending-payments/state-machine.md`
   - `docs/modules/oa-pending-payments/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around remaining OA pending payment factories/providers
   - `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
   - `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
   - `backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - `tests/test_oa_pending_payment_api.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit remaining OA pending payment app-owned surfaces:
   - service factory;
   - route factory;
   - command service factory;
   - relation repository provider;
   - payment-admitted projection/source adapter provider;
   - read-model service factory;
   - expected source-version provider;
   - refresh enqueue helper.
5. Classify each as acceptable composition/provider/platform port or select the next precise residual implementation gap.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim OA pending payment module/global closure unless the audit proves no local implementation gap remains and explicitly defers only real PostgreSQL/OA/worker/App Status/high-row/browser evidence.
- Do not weaken read-model freshness/source-version/command semantics.
- Do not broaden into unrelated `server.py` domains.
