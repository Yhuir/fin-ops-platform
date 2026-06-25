# Next Prompt

Continue after `server-py:oa-pending-payment-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:oa-pending-payment-route-owner-local-closure-audit`.
- Row365 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-oa-pending-payment-route-owner-local-closure-audit-2026-06-25.md`.
- OA pending payment local `server.py` route-owner support is accounted for after route callback collapse.
- OA pending payment module/global closure and production PostgreSQL/OA/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:oa-pending-payment-route-owner-local-closure-audit` is complete:

- remaining OA pending payment `Application` surfaces were classified as service/route/command/read-model composition, relation repository provider, projection/source adapter provider, source-version provider, refresh gateway port, auth/session adapter or shared invalidation fan-out;
- no additional OA pending payment `server.py` implementation slice was selected;
- the next residual `server.py` route-owner gap is pending invoices.

## Next Boundary

`server-py:pending-invoice-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-oa-pending-payment-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/state-machine.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around `/api/pending-invoices*` dispatch and `_handle_api_pending_invoice*` callbacks
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
   - `backend/src/fin_ops_platform/services/pending_invoice_service.py`
   - `tests/test_pending_invoice_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit remaining pending invoice app-owned route surfaces:
   - read rows/filter/detail/candidates;
   - rules and income status writes;
   - attach-existing preview/confirm single and batch;
   - export preview/download;
   - auth/session/body/export/error mapping;
   - read-model freshness and source-version ownership.
5. Select the next smallest safe implementation boundary.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim pending invoice module/global closure from this audit.
- Do not weaken pending invoice read-model freshness/source-version/attach/export/rules semantics.
- Do not broaden into unrelated `server.py` domains.
