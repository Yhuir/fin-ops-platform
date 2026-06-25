# Next Prompt

Continue after `server-py:turnover-ledger-tag-selection-write-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-tag-selection-write-route-callback-collapse`.
- Row381 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-tag-selection-write-route-callback-collapse-2026-06-25.md`.
- Turnover ledger read/export/GET and tag-selection PUT HTTP mapping now live in `TurnoverLedgerApiRoutes.route(...)`.
- `server.py` no longer defines `_handle_api_turnover_ledger_tag_selection_update(...)`.
- Remaining turnover ledger mutation callbacks are still in `Application`.
- The next selected boundary is bank-row-tags batch POST route callback collapse.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-tag-selection-write-route-callback-collapse` is complete:

- moved `PUT /api/turnover-ledger/tag-selection` session/body/actor/tenant/idempotency/error mapping into `TurnoverLedgerApiRoutes.handle_tag_selection_update_route(...)`;
- injected explicit session/body/tenant/request-boundary ports from `Application`;
- removed `_handle_api_turnover_ledger_tag_selection_update(...)`;
- kept bank-row-tags, relation-extra, confirm, closure and withdraw callbacks unchanged;
- updated source-inspect and platform Guard tests;
- verified targeted tag-selection regressions and full `tests.test_turnover_ledger_api`.

## Next Boundary

`server-py:turnover-ledger-bank-row-tags-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-tag-selection-write-route-callback-collapse-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only `POST /api/turnover-ledger/bank-row-tags/batch` route-owner collapse:
   - move body shape validation, session/body/actor/tenant/idempotency/error mapping into `TurnoverLedgerApiRoutes`;
   - use the already injected session/body/tenant ports where possible;
   - inject or reuse explicit `bank_row_tags_request_boundary_provider`;
   - remove `_handle_api_turnover_ledger_bank_row_tags_batch(...)`;
   - keep relation-extra, confirm, closure and withdraw callbacks unchanged.
4. Update tests:
   - adapt source-inspect bank-row-tags tests from `Application._handle_api_turnover_ledger_bank_row_tags_batch` to the route-owner method;
   - update platform Guard so bank-row-tags callback is removed while relation-extra/confirm/closure/withdraw callbacks remain;
   - run targeted bank-row-tags API regressions and relevant Guard tests.
5. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not migrate relation-extra, confirm, closure or withdraw callbacks in this slice.
- Do not change target validation, affected-months resolution, idempotency, stale preconditions, operation barrier targets, Workbench relation command boundaries, export limits or freshness semantics.
- Do not pass the whole `Application` into `TurnoverLedgerApiRoutes`.
- Do not make route owner import `app.auth` or directly parse HTTP cookie/header internals.
