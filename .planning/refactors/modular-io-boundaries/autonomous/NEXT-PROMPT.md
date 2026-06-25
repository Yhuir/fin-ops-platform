# Next Prompt

Continue after `server-py:bank-details-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:bank-details-route-owner-local-closure-audit`.
- Row394 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-route-owner-local-closure-audit-2026-06-25.md`.
- Migrated bank-details callbacks are gone from `server.py`.
- Bank-details route-owner closure is not claimed because `PATCH /api/bank-details/transactions/categories` still lives in `server.py`.
- Bank-details module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:bank-details-route-owner-local-closure-audit` is complete as analysis-only:

- proved migrated `_handle_api_bank_details*` / `_handle_api_bank_detail_category*` callbacks are gone;
- found remaining `PATCH /api/bank-details/transactions/categories` app-owned mapping;
- selected transaction categories route callback collapse next;
- avoided runtime code changes and avoided production validation.

## Next Boundary

`server-py:bank-details-transaction-categories-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_bank_details.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only the transaction categories PATCH slice:
   - move `PATCH /api/bank-details/transactions/categories` HTTP mapping into route owner;
   - inject/reuse explicit session, JSON body and JSON response ports;
   - remove `_handle_api_bank_transaction_categories(...)`;
   - preserve disabled bulk category mutation semantics and tests.
4. Update tests/Guard/docs/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not change bulk category mutation business semantics.
- Do not change bank detail read model, refresh, dirty/outbox, cache, frontend behavior or production data.
- Do not run production validation or mutation.
- Do not claim bank-details route-owner closure until the PATCH path is migrated and audited.
