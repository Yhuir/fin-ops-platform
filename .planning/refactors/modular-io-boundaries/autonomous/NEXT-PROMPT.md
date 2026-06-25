# Next Prompt

Continue after `server-py:turnover-ledger-relation-withdraw-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-relation-withdraw-route-callback-collapse`.
- Row387 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-relation-withdraw-route-callback-collapse-2026-06-25.md`.
- Turnover ledger read/export/GET, tag-selection PUT, bank-row-tags batch POST, relation-extra PUT, relation confirm POST, closure confirm POST, closure withdraw POST and relation withdraw POST HTTP mapping now live in `TurnoverLedgerApiRoutes.route(...)`.
- `server.py` no longer defines any `_handle_api_turnover_ledger*` route callback.
- The next selected boundary is turnover ledger route-owner local closure audit.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-relation-withdraw-route-callback-collapse` is complete:

- moved `POST /api/turnover-ledger/relations/{relation_id}/withdraw` relation-id extraction, session/body/actor/tenant/idempotency/stale-precondition/error mapping into `TurnoverLedgerApiRoutes.handle_withdraw_relation_route(...)`;
- injected explicit `withdraw_request_boundary_provider` from `Application`;
- removed `_handle_api_turnover_ledger_withdraw(...)`;
- updated source-inspect and platform Guard tests so no turnover ledger route callback remains retained in `server.py`;
- verified targeted withdraw regressions and full `tests.test_turnover_ledger_api`.

## Next Boundary

`server-py:turnover-ledger-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-relation-withdraw-route-callback-collapse-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Perform analysis only:
   - prove no `_handle_api_turnover_ledger*` route callback remains in `server.py`;
   - classify remaining turnover ledger `Application` methods as composition-root, provider, platform adapter, local runtime support, source-version/freshness/read-model provider, or remaining implementation gap;
   - decide whether the next local boundary should be another turnover ledger support extraction or a new server.py module audit.
4. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change runtime code unless the audit finds a narrow safe local implementation gap and the state machine is updated first.
- Do not claim turnover ledger module/global closure from route-owner closure alone.
- Do not hide remaining read model/worker/production evidence gaps behind local route-owner completion.
