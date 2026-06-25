# Next Prompt

Continue after `server-py:pending-invoice-read-export-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:pending-invoice-read-export-route-callback-collapse`.
- Row367 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-read-export-route-callback-collapse-2026-06-25.md`.
- Pending invoice rows/filter-options/candidates/batch-candidates/detail/export-preview/export HTTP mapping now lives in `PendingInvoiceApiRoutes.route(...)`.
- Remaining pending invoice server callbacks are write-oriented rules, attach-existing and income-status paths.
- Pending invoice module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:pending-invoice-read-export-route-callback-collapse` is complete:

- added route-owner dispatch and platform ports to `PendingInvoiceApiRoutes`;
- removed migrated app-owned read/detail/candidate/export callbacks from `server.py`;
- preserved read-model fresh-gate and export audit/XLSX response semantics through explicit ports;
- added a static platform runtime boundary Guard.

## Next Boundary

`server-py:pending-invoice-write-route-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-read-export-route-callback-collapse-2026-06-25.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/state-machine.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around remaining pending invoice callbacks
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `tests/test_pending_invoice_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit the remaining callbacks:
   - `GET /api/pending-invoices/rules`
   - `PUT /api/pending-invoices/rules`
   - `POST /api/pending-invoices/rows/{transaction_id}/attach-existing-invoice/preview`
   - `POST /api/pending-invoices/rows/{transaction_id}/attach-existing-invoice`
   - `POST /api/pending-invoices/attach-existing-invoices/preview`
   - `POST /api/pending-invoices/attach-existing-invoices`
   - `PUT /api/pending-invoices/rows/{transaction_id}/income-status`
   - `PUT /api/pending-invoices/income-statuses`
4. Classify permission, write-session, body parsing, persist-state, idempotency, audit, command-log recovery and read-model invalidation ownership before selecting the next implementation slice.
5. Update tests/guards/docs/state and commit/push if verification passes.

## Stop Gates

- Do not change pending invoice rules, attach-existing or income-status business behavior during the audit slice.
- Do not migrate write callbacks until the transaction/persist-state/recovery boundary is explicit.
- Do not run production validation or mutation.
- Do not claim pending invoice module/global closure from this slice.
- Do not broaden into unrelated `server.py` domains.
