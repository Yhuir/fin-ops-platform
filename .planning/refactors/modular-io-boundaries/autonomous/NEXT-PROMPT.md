# Next Prompt

Continue after `server-py:workbench-events-active-stream-registry-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-events-active-stream-registry-extraction`.
- Row413 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-events-active-stream-registry-extraction-2026-06-25.md`.
- `WorkbenchEventsActiveStreamRegistry` now owns Workbench SSE active stream count/lock management.
- Refresh-status payload normalization and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-events-active-stream-registry-extraction` is complete:

- added `WorkbenchEventsActiveStreamRegistry`;
- moved Workbench SSE active stream count/lock management out of `Application`;
- wired `WorkbenchEventsApiRoutes` through registry `mark_started`/`mark_closed` ports;
- preserved stream close cleanup behavior through existing SSE tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-read-route-owner-post-stream-registry-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-events-active-stream-registry-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `backend/src/fin_ops_platform/services/workbench_events_active_stream_registry.py`
   - `tests/test_workbench_sql_runtime.py` Workbench events tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - refresh-status payload normalization and event-name mapping;
   - legacy `/api/workbench` SQL fallback and payload builder path.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
