# Next Prompt

Continue after `server-py:bank-details-write-route-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:bank-details-write-route-callback-audit`.
- Row391 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-write-route-callback-audit-2026-06-25.md`.
- Bank details read/export route callbacks are already migrated into `BankDetailsApiRoutes.route(...)`.
- Remaining write callbacks were split into auto-tag and category groups.
- Next selected implementation boundary: `server-py:bank-details-auto-tag-write-route-callback-collapse`.
- Bank-details module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:bank-details-write-route-callback-audit` is complete as analysis-only:

- audited remaining bank details write callbacks in `server.py`;
- selected auto-tag PUT/reapply/file-replacement as the next implementation slice;
- deferred category confirmation/assignment callbacks to a later slice;
- avoided runtime code changes and avoided production validation.

## Next Boundary

`server-py:bank-details-auto-tag-write-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-write-route-callback-audit-2026-06-25.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_bank_details.py`
   - `tests/test_bank_auto_tag_rules_api.py`
   - `tests/test_bank_details_routes.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only the auto-tag write slice:
   - move `PUT /api/bank-details/auto-tag-rules`, `POST /api/bank-details/auto-tag-rules/reapply` and `POST /api/bank-details/auto-tag-rules/file-replacement` HTTP mapping into `BankDetailsApiRoutes.route(...)`;
   - inject explicit session, JSON body, default bundled rules source and JSON response ports;
   - remove corresponding app callbacks from `server.py`;
   - keep category confirmation/assignment callbacks in `server.py` for later.
4. Update tests/Guard/docs/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not move category confirmation/assignment callbacks in this slice.
- Do not change bank detail read model, refresh, dirty/outbox, cache, business rules or frontend behavior.
- Do not run production validation or mutation.
- Do not claim bank details module/global closure.
