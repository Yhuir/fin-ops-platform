# Next Prompt

Continue after `server-py:bank-details-read-export-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:bank-details-read-export-route-callback-collapse`.
- Row390 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-read-export-route-callback-collapse-2026-06-25.md`.
- Bank details accounts, transactions, transactions export and auto-tag-rules GET HTTP mapping now live in `BankDetailsApiRoutes.route(...)`.
- The migrated read/export app callbacks were removed from `server.py`.
- Bank details write callbacks remain in `server.py` for a dedicated follow-up audit.
- Bank-details module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:bank-details-read-export-route-callback-collapse` is complete:

- added `BankDetailsApiRoutes.route(...)` for read/export HTTP mapping;
- injected explicit read-session, JSON response and export response ports from `Application`;
- removed read/export callbacks from `server.py`;
- updated route tests, runtime bootstrap tests and platform Guard coverage;
- avoided bank details write callback migration and avoided production validation.

## Next Boundary

`server-py:bank-details-write-route-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-read-export-route-callback-collapse-2026-06-25.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_bank_details.py`
   - `tests/test_bank_auto_tag_rules_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Perform analysis only:
   - audit remaining bank details write callbacks;
   - split auto-tag PUT/reapply/file replacement from category confirmation/assignment if risk suggests multiple implementation slices;
   - identify required route-owner ports for session, JSON body, default bundled rules source, persistence/side-effect preservation and permission behavior;
   - update queue/state/next prompt with the selected bounded write slice.
4. Commit/push the audit if verification passes.

## Stop Gates

- Do not move write callbacks until the audit selects a bounded slice.
- Do not change bank detail read model, refresh, dirty/outbox, cache, business rules or frontend behavior during audit.
- Do not run production validation or mutation.
- Do not claim bank details module/global closure.
