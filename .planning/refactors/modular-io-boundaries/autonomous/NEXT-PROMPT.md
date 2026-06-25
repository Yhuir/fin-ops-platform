# Next Prompt

Continue after `server-py:pending-invoice-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:pending-invoice-route-owner-local-closure-audit`.
- Row370 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-route-owner-local-closure-audit-2026-06-25.md`.
- Pending invoice local `server.py` route-owner support is accounted for, but pending invoice module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:pending-invoice-route-owner-local-closure-audit` is complete:

- confirmed no `_handle_api_pending_invoice*` callbacks remain in `server.py`;
- classified remaining pending invoice `Application` surfaces as composition-root, auth/session, export response, error response, settings lifecycle or read-model invalidation/provider ports;
- selected tax route-owner audit as the next local server.py boundary.

## Next Boundary

`server-py:tax-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-pending-invoice-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/README.md`
   - the relevant tax module docs under `docs/modules/` and linked architecture/dev docs
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_tax.py`
   - tax-related API/service tests
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit tax-related `Application` callbacks and existing `TaxApiRoutes` route ownership.
4. Select one bounded local implementation or analysis slice.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim tax module/global closure from an audit slice.
- Do not broaden into unrelated `server.py` domains.
