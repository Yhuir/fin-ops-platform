# Next Prompt

Continue after `server-py:workbench-legacy-api-sql-read-provider-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-legacy-api-sql-read-provider-extraction`.
- Row419 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-legacy-api-sql-read-provider-extraction-2026-06-25.md`.
- `WorkbenchLegacyApiSqlReadProvider` now owns legacy `/api/workbench` SQL read-model view lookup, miss/stale/OA-sync payload mapping and refresh enqueue orchestration.
- Raw/grouped payload builder handling remains deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-legacy-api-sql-read-provider-extraction` is complete:

- added `WorkbenchLegacyApiSqlReadProvider`;
- moved legacy `/api/workbench` SQL view lookup/miss/stale/OA-sync response payload orchestration out of `Application`;
- wired `_handle_api_workbench(...)` through the provider and kept JSON response mapping in `Application`;
- removed `Application._handle_api_workbench_from_sql_read_model(...)`;
- preserved legacy `/api/workbench` SQL-first behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-legacy-api-payload-builder-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-legacy-api-sql-read-provider-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` legacy raw/grouped payload tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_build_api_workbench_payload(...)`;
   - `_build_raw_workbench_payload(...)`.
   - live/OA payload merge and retention helpers called by those builders;
   - tag/decorator helpers called after grouped payload creation.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
