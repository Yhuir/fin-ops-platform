# Next Prompt

Continue after `server-py:pending-invoice-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:pending-invoice-route-owner-audit`.
- Row366 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-route-owner-audit-2026-06-25.md`.
- Pending invoice route-owner audit split read/detail/candidate/export wrappers from rules/attach/income-status write wrappers.
- Pending invoice module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:pending-invoice-route-owner-audit` is complete:

- audited direct `/api/pending-invoices*` dispatch and `_handle_api_pending_invoice*` callbacks;
- confirmed `PendingInvoiceApiRoutes` already owns service-level methods for read/detail/candidate/export/rules/attach/income status;
- selected the first bounded implementation slice for read/detail/candidate/export HTTP mapping.

## Next Boundary

`server-py:pending-invoice-read-export-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-route-owner-audit-2026-06-25.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/state-machine.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around pending invoice dispatch/callbacks
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `tests/test_pending_invoice_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before implementation-oriented changes if more context is needed.
4. Implement:
   - add `route(method, route_path, query, body, headers)` to `PendingInvoiceApiRoutes`;
   - inject explicit read-session, JSON response, JSON body loader, error response, export audit and XLSX response ports;
   - move rows/filter-options/invoice-candidates/batch-candidates/relation-detail/bank-detail/invoice-detail/OA-detail/export-preview/export HTTP mapping into the route owner;
   - remove migrated app-owned callbacks only for that read/detail/candidate/export group;
   - leave rules, attach-existing and income-status write callbacks for separate slices.
5. Update tests/guards/docs/state and commit/push if verification passes.

## Stop Gates

- Do not change pending invoice business rules, read-model freshness/source-version contracts, attach-existing semantics, rules semantics, income-status semantics or frontend API shape.
- Do not run production validation or mutation.
- Do not claim pending invoice module/global closure from this route-owner slice.
- Do not broaden into unrelated `server.py` domains.
