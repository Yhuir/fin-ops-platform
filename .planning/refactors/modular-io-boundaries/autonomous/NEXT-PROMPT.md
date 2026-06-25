# Next Prompt

Continue after `server-py:bank-details-category-write-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:bank-details-category-write-route-callback-collapse`.
- Row393 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-category-write-route-callback-collapse-2026-06-25.md`.
- Bank details read/export, auto-tag write and category write HTTP mapping now live in `BankDetailsApiRoutes.route(...)`.
- The migrated bank-details app callbacks were removed from `server.py`.
- Bank-details module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:bank-details-category-write-route-callback-collapse` is complete:

- moved category confirmation/assignment POST/DELETE HTTP mapping into `BankDetailsApiRoutes.route(...)`;
- removed migrated category callbacks from `server.py`;
- updated route tests, auto-tag API tests and platform Guard coverage;
- avoided production validation and avoided module/global closure claim.

## Next Boundary

`server-py:bank-details-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-category-write-route-callback-collapse-2026-06-25.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_bank_details.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Perform analysis only:
   - prove no `_handle_api_bank_details*` or `_handle_api_bank_detail_category*` route callback remains in `server.py`;
   - classify remaining bank-details `Application` methods as composition-root, provider, platform adapter, local/runtime support, read-model provider or remaining implementation gap;
   - decide whether the next local boundary should be another bank-details support extraction or a new server.py module audit.
4. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim bank-details module/global closure from route-owner closure alone.
- Do not change runtime code unless the audit finds a narrow safe local implementation gap and the state machine is updated first.
