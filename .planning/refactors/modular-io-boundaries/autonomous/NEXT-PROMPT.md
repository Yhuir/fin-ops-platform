# Next Prompt

Continue after `server-py:workbench-refresh-status-payload-provider-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-refresh-status-payload-provider-extraction`.
- Row417 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-payload-provider-extraction-2026-06-25.md`.
- `WorkbenchRefreshStatusPayloadProvider` now owns SSE refresh-status repository lookup, source freshness and normalizer orchestration.
- Legacy `/api/workbench` SQL fallback/payload handling remains deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-refresh-status-payload-provider-extraction` is complete:

- added `WorkbenchRefreshStatusPayloadProvider`;
- moved SSE refresh-status repository lookup/source-freshness/normalization orchestration out of `Application`;
- wired `WorkbenchEventsApiRoutes` through `status_payload_provider.payload_for_scope`;
- removed `Application._workbench_refresh_status_payload_for_scope(...)`;
- preserved refresh-status API and SSE behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-legacy-api-sql-fallback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-payload-provider-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` legacy `/api/workbench` and SQL runtime tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_handle_api_workbench(...)`;
   - `_handle_api_workbench_from_sql_read_model(...)`;
   - `_build_api_workbench_payload(...)`;
   - `_build_raw_workbench_payload(...)`.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
