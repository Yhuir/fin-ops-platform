# Next Prompt

Continue after `server-py:bank-details-transaction-categories-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:bank-details-transaction-categories-route-callback-collapse`.
- Row395 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-transaction-categories-route-callback-collapse-2026-06-25.md`.
- Disabled `PATCH /api/bank-details/transactions/categories` is now owned by `BankDetailsApiRoutes.route(...)`.
- `_handle_api_bank_transaction_categories(...)` is removed from `server.py`.
- The 410 `manual_bank_transaction_category_disabled` no-mutation behavior is covered by route-owner tests and static Guard.
- Bank-details route-owner closure, module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:bank-details-transaction-categories-route-callback-collapse` is complete locally:

- moved the disabled PATCH mapping into the bank-details route owner;
- removed the app-owned handler and dispatch branch;
- preserved disabled bulk category mutation semantics;
- updated tests, Guard, docs and autonomous state.

## Next Boundary

`server-py:bank-details-route-owner-local-closure-audit-retry`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-transaction-categories-route-callback-collapse-2026-06-25.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/implementation-notes.md`
   - `docs/modules/bank-details/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_bank_details.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit only bank-details route ownership:
   - prove no `_handle_api_bank_details*`, `_handle_api_bank_detail_category*` or `_handle_api_bank_transaction_categories` callbacks remain in `server.py`;
   - confirm `/api/bank-details/...` dispatch delegates to `BankDetailsApiRoutes.route(...)`;
   - classify remaining `Application` surfaces as composition-root, provider, auth/session, HTTP adapter, read-model/source-version/refresh or platform ports;
   - do not claim module/global closure unless all local implementation definitions are actually satisfied.
4. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change bank detail business behavior, read model, refresh, dirty/outbox, cache, frontend behavior or production data.
- Do not claim global closure.
- If a remaining bank-details app-owned callback or implementation helper is found, select the next narrow local implementation boundary instead of closing.
