# Next Prompt

Continue after `server-py:pending-invoice-write-route-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:pending-invoice-write-route-callback-audit`.
- Row368 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-write-route-callback-audit-2026-06-25.md`.
- Pending invoice read/detail/candidate/export HTTP mapping already lives in `PendingInvoiceApiRoutes.route(...)`.
- Remaining pending invoice rules, attach-existing and income-status callbacks are thin HTTP body/session/error/JSON/persist wrappers.
- Pending invoice module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:pending-invoice-write-route-callback-audit` is complete:

- classified rules GET/PUT, attach-existing preview/confirm and income-status update callbacks;
- confirmed business logic already lives in `PendingInvoiceApiRoutes`, `PendingInvoiceApplicationService` and `PendingInvoiceRulesApplicationService`;
- selected full write route callback collapse with explicit write-session and persist-state ports.

## Next Boundary

`server-py:pending-invoice-write-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-write-route-callback-audit-2026-06-25.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/state-machine.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around remaining pending invoice callbacks
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `tests/test_pending_invoice_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement:
   - add write-session and persist-state ports to `PendingInvoiceApiRoutes`;
   - route-owner mapping for rules GET/PUT;
   - route-owner mapping for attach-existing single/batch preview and confirm;
   - route-owner mapping for income-status single/batch update;
   - remove migrated app callbacks;
   - extend static Guard coverage for the removed callbacks.
4. Verify with py_compile, `tests.test_pending_invoice_api`, targeted platform runtime boundary guards, docs verify and diff checks.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not change rules, attach-existing or income-status business behavior.
- Preserve write-session permission mapping and `_persist_state()` semantics.
- Do not run production validation or mutation.
- Do not claim pending invoice module/global closure from this slice.
- Do not broaden into unrelated `server.py` domains.
