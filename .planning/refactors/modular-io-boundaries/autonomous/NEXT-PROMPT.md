# Next Prompt

Continue after `server-py:turnover-ledger-read-export-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-read-export-route-callback-collapse`.
- Row379 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-read-export-route-callback-collapse-2026-06-25.md`.
- Turnover ledger read/export/GET HTTP mapping now lives in `TurnoverLedgerApiRoutes.route(...)`.
- `server.py` no longer defines the migrated read/export GET callbacks.
- Mutation callbacks remain in `Application` for a dedicated write-boundary audit.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-read-export-route-callback-collapse` is complete:

- added `TurnoverLedgerApiRoutes.route(...)`;
- moved list/grouped ledger GET, export preview/export GET, tag-selection GET, relation detail GET and relation extra GET HTTP mapping into the route owner;
- injected `json_response`, `export_response` and `tag_selection_provider` as explicit route ports;
- removed migrated app-owned GET callbacks and query helpers from `server.py`;
- added `test_turnover_ledger_read_export_routes_use_route_owner`;
- updated the export limit API test to inject failures through the new route-owner boundary;
- verified targeted read facade, API and static Guard coverage locally.

## Next Boundary

`server-py:turnover-ledger-write-route-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-read-export-route-callback-collapse-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit only the remaining turnover ledger PUT/POST callbacks:
   - tag-selection PUT;
   - bank-row-tags batch POST;
   - relation extra PUT;
   - relation confirm POST;
   - closure confirm POST;
   - closure withdraw POST;
   - relation withdraw POST.
4. Decide the smallest next implementation boundary: direct route-owner callback collapse, or first extracting a service/request boundary if route code would otherwise own business side effects.
5. Update analysis/state/queue/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not migrate write callbacks during the audit slice unless the audit explicitly selects and scopes an implementation boundary.
- Do not change turnover ledger write behavior, idempotency, stale preconditions, operation barrier targets, Workbench relation command boundaries, export limits or freshness semantics.
- Do not broaden into unrelated domains.
