# Next Prompt

Continue after `server-py:output-invoice-collection-post-fresh-gate-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:output-invoice-collection-post-fresh-gate-local-closure-audit`.
- Row362 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-post-fresh-gate-local-closure-audit-2026-06-25.md`.
- Output collection local `server.py` support is accounted for after route-owner collapse and read-model fresh-gate extraction.
- Output collection module/global closure and production PostgreSQL/worker/App Status/high-row/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:output-invoice-collection-post-fresh-gate-local-closure-audit` is complete:

- remaining output collection `Application` surfaces were classified as composition-root, HTTP adapter, auth/session, source-version, refresh gateway, import-scope or shared invalidation provider ports;
- no additional output collection `server.py` implementation slice was selected;
- the next residual `server.py` route-owner gap is OA pending payment.

## Next Boundary

`server-py:oa-pending-payment-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-post-fresh-gate-local-closure-audit-2026-06-25.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/oa-pending-payments/state-machine.md`
   - `docs/modules/oa-pending-payments/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around `/api/oa-pending-payments*` dispatch and `_handle_api_oa_pending_payments*` callbacks
   - `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
   - `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
   - `backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py`
   - `tests/test_oa_pending_payment_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit remaining OA pending payment app-owned route surfaces:
   - identify which callbacks are thin HTTP/session/body/error mapping around route-owner/service methods;
   - identify whether any business, read-model freshness, source-version, command, queue or payload logic remains app-owned;
   - split read-only routes, candidate/detail routes and mutation/command routes if needed;
   - select the next smallest safe implementation boundary.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim OA pending payment module/global closure from local audit.
- Do not weaken read-model refreshing/source-version/fail-closed behavior.
- Do not broaden into unrelated `server.py` domains.
