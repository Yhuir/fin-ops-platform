# Next Prompt

Continue after `server-py:turnover-ledger-bank-row-tags-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-bank-row-tags-route-callback-collapse`.
- Row382 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-bank-row-tags-route-callback-collapse-2026-06-25.md`.
- Turnover ledger read/export/GET, tag-selection PUT and bank-row-tags batch POST HTTP mapping now live in `TurnoverLedgerApiRoutes.route(...)`.
- `server.py` no longer defines `_handle_api_turnover_ledger_tag_selection_update(...)` or `_handle_api_turnover_ledger_bank_row_tags_batch(...)`.
- Remaining turnover ledger mutation callbacks are relation-extra, confirm, closure and withdraw callbacks in `Application`.
- The next selected boundary is relation-extra PUT route callback collapse.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-bank-row-tags-route-callback-collapse` is complete:

- moved `POST /api/turnover-ledger/bank-row-tags/batch` body shape validation, session/body/actor/tenant/idempotency/error mapping into `TurnoverLedgerApiRoutes.handle_bank_row_tags_batch_route(...)`;
- injected explicit `bank_row_tags_request_boundary_provider` from `Application`;
- removed `_handle_api_turnover_ledger_bank_row_tags_batch(...)`;
- kept relation-extra, confirm, closure and withdraw callbacks unchanged;
- updated source-inspect and platform Guard tests;
- verified targeted bank-row-tags regressions and full `tests.test_turnover_ledger_api`.

## Next Boundary

`server-py:turnover-ledger-relation-extra-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-bank-row-tags-route-callback-collapse-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only `PUT /api/turnover-ledger/relations/{relation_id}/extra` route-owner collapse:
   - move payload object validation, session/body/actor/error mapping into `TurnoverLedgerApiRoutes`;
   - use already injected session/body ports where possible;
   - inject or reuse explicit `relation_extra_request_boundary_provider` and precondition error payload mapper;
   - remove `_handle_api_turnover_ledger_relation_extra_update(...)`;
   - keep confirm, closure and withdraw callbacks unchanged.
4. Update tests:
   - adapt source-inspect relation-extra tests from `Application._handle_api_turnover_ledger_relation_extra_update` to the route-owner method;
   - update platform Guard so relation-extra callback is removed while confirm/closure/withdraw callbacks remain;
   - run targeted relation-extra API regressions and relevant Guard tests.
5. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not migrate confirm, closure or withdraw callbacks in this slice.
- Do not change stale preconditions, idempotency, operation barrier targets, Workbench relation command boundaries, export limits or freshness semantics.
- Do not pass the whole `Application` into `TurnoverLedgerApiRoutes`.
- Do not make route owner import `app.auth` or directly parse HTTP cookie/header internals.
