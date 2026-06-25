# Next Prompt

Continue after `server-py:bank-details-auto-tag-write-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:bank-details-auto-tag-write-route-callback-collapse`.
- Row392 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-auto-tag-write-route-callback-collapse-2026-06-25.md`.
- Bank details read/export and auto-tag write HTTP mapping now live in `BankDetailsApiRoutes.route(...)`.
- The migrated auto-tag app callbacks were removed from `server.py`.
- Bank details category confirmation/assignment callbacks remain in `server.py` for the next slice.
- Bank-details module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:bank-details-auto-tag-write-route-callback-collapse` is complete:

- moved PUT/reapply/file-replacement HTTP mapping into `BankDetailsApiRoutes.route(...)`;
- injected explicit session, JSON body, default bundled rules source and JSON response ports;
- removed migrated auto-tag callbacks from `server.py`;
- updated route tests, auto-tag API tests and platform Guard coverage;
- avoided category callback migration and avoided production validation.

## Next Boundary

`server-py:bank-details-category-write-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-auto-tag-write-route-callback-collapse-2026-06-25.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_bank_details.py`
   - `tests/test_bank_auto_tag_rules_api.py`
   - `tests/test_bank_details_routes.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only the category write slice:
   - move category confirmation/assignment POST/DELETE HTTP mapping into `BankDetailsApiRoutes.route(...)`;
   - inject or reuse explicit session, JSON body and JSON response ports;
   - remove corresponding app callbacks from `server.py`;
   - preserve permission, invalid body and category validation error semantics.
4. Update tests/Guard/docs/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not change bank detail read model, refresh, dirty/outbox, cache, business rules or frontend behavior.
- Do not run production validation or mutation.
- Do not claim bank details module/global closure.
