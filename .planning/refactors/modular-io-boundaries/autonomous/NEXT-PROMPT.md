# Next Prompt

Continue after `server-py:turnover-ledger-relation-extra-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-relation-extra-route-callback-collapse`.
- Row383 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-relation-extra-route-callback-collapse-2026-06-25.md`.
- Turnover ledger read/export/GET, tag-selection PUT, bank-row-tags batch POST and relation-extra PUT HTTP mapping now live in `TurnoverLedgerApiRoutes.route(...)`.
- `server.py` no longer defines `_handle_api_turnover_ledger_relation_extra_update(...)`.
- Remaining turnover ledger mutation callbacks are relation confirm, closure confirm, closure withdraw and relation withdraw callbacks in `Application`.
- The next selected boundary is relation confirm route callback collapse.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-relation-extra-route-callback-collapse` is complete:

- moved `PUT /api/turnover-ledger/relations/{relation_id}/extra` payload object validation, session/body/actor/tenant/idempotency/stale-precondition/error mapping into `TurnoverLedgerApiRoutes.handle_relation_extra_update_route(...)`;
- injected explicit `relation_extra_request_boundary_provider`, `relation_extra_tenant_id_provider` and `write_precondition_error_payload` from `Application`;
- removed `_handle_api_turnover_ledger_relation_extra_update(...)`;
- kept confirm, closure and withdraw callbacks unchanged;
- updated source-inspect and platform Guard tests;
- verified targeted relation-extra regressions and full `tests.test_turnover_ledger_api`.

## Next Boundary

`server-py:turnover-ledger-confirm-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-relation-extra-route-callback-collapse-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only `POST /api/turnover-ledger/relations/confirm` route-owner collapse:
   - move payload object validation, session/body/actor/tenant/idempotency/error mapping into `TurnoverLedgerApiRoutes`;
   - inject or reuse explicit confirm request-boundary provider and precondition error payload mapper;
   - preserve affected-months, stale precondition and write response behavior;
   - remove `_handle_api_turnover_ledger_confirm(...)`;
   - keep closure confirm, closure withdraw and relation withdraw callbacks unchanged.
4. Update tests:
   - adapt source-inspect confirm tests from `Application._handle_api_turnover_ledger_confirm` to the route-owner method;
   - update platform Guard so confirm callback is removed while closure/withdraw callbacks remain;
   - run targeted confirm API regressions and relevant Guard tests.
5. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not migrate closure confirm, closure withdraw or relation withdraw callbacks in this slice.
- Do not change stale preconditions, idempotency, operation barrier targets, Workbench relation command boundaries, export limits or freshness semantics.
- Do not pass the whole `Application` into `TurnoverLedgerApiRoutes`.
- Do not make route owner import `app.auth` or directly parse HTTP cookie/header internals.
