# Next Prompt

Continue after `server-py:turnover-ledger-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:turnover-ledger-route-owner-audit`.
- Row378 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-route-owner-audit-2026-06-25.md`.
- Turnover ledger read/export/GET callbacks are selected for the first bounded route-owner collapse.
- Mutation callbacks remain in `Application` for later dedicated write-boundary audits.
- Turnover ledger module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.

## Previous Prompt Completion

`server-py:turnover-ledger-route-owner-audit` is complete:

- audited `/api/turnover-ledger*` dispatch branches and callbacks;
- split thin read/export/GET callbacks from thicker mutation callbacks;
- selected read/export route callback collapse as the next local-first implementation boundary.

## Next Boundary

`server-py:turnover-ledger-read-export-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-turnover-ledger-route-owner-audit-2026-06-25.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
   - `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_turnover_ledger_read_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only the read/export/GET route-owner slice:
   - list/grouped ledger GET;
   - export preview/export GET;
   - tag-selection GET;
   - relation detail GET;
   - relation extra GET.
4. Leave mutation callbacks unchanged.
5. Add/update Guard and targeted API/read-facade tests, then update docs/state and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not migrate mutation callbacks in this slice.
- Do not change turnover ledger write behavior, stale preconditions, operation barrier targets, Workbench relation command boundaries, export limits or freshness semantics.
- Do not broaden into unrelated domains.
