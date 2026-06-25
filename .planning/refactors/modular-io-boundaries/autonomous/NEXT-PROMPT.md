# Next Prompt

Continue after `planning:post-turnover-ledger-route-owner-next-boundary-selection`.

## Current State

- Branch: `dev`.
- Last completed boundary: `planning:post-turnover-ledger-route-owner-next-boundary-selection`.
- Row389 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/post-turnover-ledger-route-owner-next-boundary-selection-2026-06-25.md`.
- Next selected implementation boundary: `server-py:bank-details-read-export-route-callback-collapse`.
- Scope is local-first: no production validation, no Go hot-path, no global module closure claim.

## Previous Prompt Completion

`planning:post-turnover-ledger-route-owner-next-boundary-selection` is complete as analysis-only:

- compared remaining `server.py` route/support surfaces after turnover ledger route-owner closure;
- selected bank details read/export route callback collapse as the next bounded local implementation slice;
- left bank details write callbacks for later slices;
- avoided runtime code changes and avoided production validation.

## Next Boundary

`server-py:bank-details-read-export-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/post-turnover-ledger-route-owner-next-boundary-selection-2026-06-25.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_bank_details.py`
   - `tests/test_bank_details_routes.py`
   - `tests/test_bank_auto_tag_rules_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only the read/export slice:
   - move `/api/bank-details/accounts`, `/api/bank-details/transactions`, `/api/bank-details/transactions/export` and `GET /api/bank-details/auto-tag-rules` HTTP mapping into `BankDetailsApiRoutes.route(...)`;
   - inject explicit read-session/json/export ports as needed;
   - remove corresponding app callbacks from `server.py`;
   - keep auto-tag PUT/reapply/file-replacement and category confirmation/assignment callbacks in `server.py` for later write slices.
4. Update tests/Guard/docs/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not move bank details write callbacks in this slice.
- Do not change bank detail read model, refresh, dirty/outbox, cache, business rules or frontend behavior.
- Do not run production validation or mutation.
- Do not claim bank details module/global closure.
