# Next Prompt

Continue after `server-py:turnover-ledger-closure-withdraw-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-closure-withdraw-route-callback-collapse`.
- Row386 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-closure-withdraw-route-callback-collapse-2026-06-25.md`.
- Turnover ledger read/export/GET, tag-selection PUT, bank-row-tags batch POST, relation-extra PUT, relation confirm POST, closure confirm POST and closure withdraw POST HTTP mapping now live in `TurnoverLedgerApiRoutes.route(...)`.
- `server.py` no longer defines `_handle_api_turnover_ledger_closure_withdraw(...)`.
- Remaining turnover ledger mutation callback is relation withdraw in `Application`.
- The next selected boundary is relation withdraw route callback collapse.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-closure-withdraw-route-callback-collapse` is complete:

- moved `POST /api/turnover-ledger/closures/withdraw` session/body/actor/tenant/idempotency/error mapping into `TurnoverLedgerApiRoutes.handle_closure_withdraw_route(...)`;
- reused explicit `closure_request_boundary_provider` from `Application` with dynamic override semantics;
- removed `_handle_api_turnover_ledger_closure_withdraw(...)`;
- kept relation withdraw callback unchanged;
- added source-inspect and platform Guard tests;
- verified targeted closure withdraw regressions and full `tests.test_turnover_ledger_api`.

## Next Boundary

`server-py:turnover-ledger-relation-withdraw-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-closure-withdraw-route-callback-collapse-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only `POST /api/turnover-ledger/relations/{relation_id}/withdraw` route-owner collapse:
   - move relation id extraction, session/body/actor/tenant/idempotency/error mapping into `TurnoverLedgerApiRoutes`;
   - inject or reuse explicit withdraw request-boundary provider and precondition error payload mapper;
   - preserve unknown relation handling, expected_versions, affected-months, stale precondition and write response behavior;
   - remove `_handle_api_turnover_ledger_withdraw(...)`.
4. Update tests:
   - adapt source-inspect withdraw tests from `Application._handle_api_turnover_ledger_withdraw` to the route-owner method;
   - update platform Guard so no turnover ledger route callback remains in `server.py`;
   - run targeted withdraw API regressions and relevant Guard tests.
5. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change stale preconditions, idempotency, operation barrier targets, Workbench relation command boundaries, export limits or freshness semantics.
- Do not pass the whole `Application` into `TurnoverLedgerApiRoutes`.
- Do not make route owner import `app.auth` or directly parse HTTP cookie/header internals.
