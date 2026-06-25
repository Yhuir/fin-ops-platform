# Next Prompt

Continue after `server-py:pending-invoice-write-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:pending-invoice-write-route-callback-collapse`.
- Row369 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-write-route-callback-collapse-2026-06-25.md`.
- Pending invoice read/detail/candidate/export/rules/attach/income-status HTTP mapping now lives in `PendingInvoiceApiRoutes.route(...)`.
- Pending invoice module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:pending-invoice-write-route-callback-collapse` is complete:

- added write-session and persist-state ports to `PendingInvoiceApiRoutes`;
- moved remaining pending invoice rules, attach-existing and income-status HTTP mapping into the route owner;
- removed migrated app callbacks from `server.py`;
- preserved persist-state behavior for attach and income write paths;
- extended static Guard coverage.

## Next Boundary

`server-py:pending-invoice-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-write-route-callback-collapse-2026-06-25.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/state-machine.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining pending invoice `Application` surfaces after route callback collapse:
   - route factory/composition;
   - read/write session provider;
   - export response/audit port;
   - read-model source-version/settings providers;
   - shared persist-state and refresh/invalidation ports.
4. Decide whether pending invoice local `server.py` route-owner support is accounted for, without claiming global/module production closure.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim pending invoice module/global closure unless all local and evidence gates are explicitly satisfied.
- Do not broaden into unrelated `server.py` domains.
