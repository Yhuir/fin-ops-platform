# Next Prompt

Continue after `server-py:turnover-ledger-write-route-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-write-route-callback-audit`.
- Row380 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-write-route-callback-audit-2026-06-25.md`.
- Turnover ledger read/export/GET HTTP mapping already lives in `TurnoverLedgerApiRoutes.route(...)`.
- Remaining turnover ledger mutation callbacks are still in `Application`.
- The audit selected tag-selection PUT as the smallest next implementation slice.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-write-route-callback-audit` is complete:

- audited tag-selection PUT, bank-row-tags batch POST, relation extra PUT, relation confirm POST, closure confirm POST, closure withdraw POST and relation withdraw POST;
- confirmed existing request-boundary facades already own most business normalization, affected-months, stale/idempotency and legacy fallback behavior;
- selected only `PUT /api/turnover-ledger/tag-selection` for the next route callback collapse;
- deferred bank-row-tags, relation-extra, confirm, closure and withdraw groups to later slices.

## Next Boundary

`server-py:turnover-ledger-tag-selection-write-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-write-route-callback-audit-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only `PUT /api/turnover-ledger/tag-selection` route-owner collapse:
   - move session/body/actor/tenant/idempotency/error mapping into `TurnoverLedgerApiRoutes`;
   - inject explicit ports from `Application`;
   - remove `_handle_api_turnover_ledger_tag_selection_update(...)`;
   - keep all other turnover ledger mutation callbacks unchanged.
4. Update tests:
   - adapt source-inspect tag-selection tests from `Application._handle_api_turnover_ledger_tag_selection_update` to the route-owner method;
   - update platform Guard so tag-selection PUT callback is removed while other mutation callbacks remain;
   - run targeted tag-selection API regressions and relevant Guard tests.
5. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not migrate bank-row-tags, relation-extra, confirm, closure or withdraw callbacks in this slice.
- Do not change turnover ledger write behavior, idempotency, stale preconditions, operation barrier targets, Workbench relation command boundaries, export limits or freshness semantics.
- Do not pass the whole `Application` into `TurnoverLedgerApiRoutes`.
- Do not make route owner import `app.auth` or directly parse HTTP cookie/header internals.
