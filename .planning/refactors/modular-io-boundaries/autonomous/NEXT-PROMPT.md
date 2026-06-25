# Next Prompt

Continue after `server-py:workbench-read-route-owner-post-refresh-status-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-read-route-owner-post-refresh-status-audit`.
- Row410 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-refresh-status-audit-2026-06-25.md`.
- Selected next local implementation boundary: `server-py:workbench-events-stream-route-owner-extraction`.
- Refresh-status payload normalization and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-read-route-owner-post-refresh-status-audit` is complete:

- audited remaining Workbench read-route `Application` surfaces;
- selected `GET /api/workbench/events` SSE stream route owner as the next narrow local implementation boundary;
- deferred refresh-status payload normalization because it is shared by SSE/App Health/runtime status;
- deferred legacy `/api/workbench` SQL fallback and payload builder as a larger read-model gateway/service boundary;
- avoided production validation.

## Next Boundary

`server-py:workbench-events-stream-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-refresh-status-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` Workbench events handler and stream helpers
   - `tests/test_workbench_sql_runtime.py` Workbench events tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Introduce an explicit Workbench events stream route owner with ports for scope key, status payload, event name, SSE serialization, lifecycle start/close and sleep.
4. Update `_handle_api_workbench_events(...)` to delegate stream construction while preserving `Application` response contract or explicit response metadata.
5. Preserve heartbeat shape, no-buffering headers, polling-without-Redis behavior and stream close cleanup.
6. Add route-owner/static Guard coverage and rerun existing Workbench events tests.
7. Do not move refresh-status payload normalization or legacy `/api/workbench` SQL fallback.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move refresh-status payload normalization or legacy `/api/workbench` SQL fallback in the SSE route-owner slice.
