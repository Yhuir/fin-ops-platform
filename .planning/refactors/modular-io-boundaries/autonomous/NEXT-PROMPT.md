# Next Prompt

Continue after `server-py:workbench-events-stream-route-owner-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-events-stream-route-owner-extraction`.
- Row411 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-events-stream-route-owner-extraction-2026-06-25.md`.
- `WorkbenchEventsApiRoutes` now owns Workbench SSE stream body/header mapping behind explicit ports.
- Refresh-status payload normalization and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-events-stream-route-owner-extraction` is complete:

- added `WorkbenchEventsApiRoutes`;
- moved `GET /api/workbench/events` stream body/header mapping out of `Application`;
- preserved heartbeat, no-buffering headers, polling-without-Redis behavior and stream close cleanup;
- kept refresh-status payload normalization and active stream registry helpers as explicit ports;
- added static Guard coverage and reused existing Workbench SSE tests;
- avoided production validation.

## Next Boundary

`server-py:workbench-read-route-owner-post-events-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-events-stream-route-owner-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` Workbench events tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - refresh-status payload normalization/helper ownership;
   - active stream registry helper ownership after events route extraction;
   - legacy `/api/workbench` SQL fallback and payload builder path.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
