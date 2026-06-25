# Next Prompt

Continue after `server-py:workbench-read-route-owner-post-groups-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-read-route-owner-post-groups-audit`.
- Row408 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-groups-audit-2026-06-25.md`.
- Selected next local implementation boundary: `server-py:workbench-refresh-status-route-owner-extraction`.
- SSE events and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-read-route-owner-post-groups-audit` is complete:

- audited remaining Workbench read-route `Application` surfaces;
- classified `/api/workbench/refresh-status` as a thin facade delegate suitable for route-owner extraction;
- deferred `/api/workbench/events` because it owns SSE stream lifecycle;
- deferred legacy `/api/workbench` because it owns SQL fallback, refresh enqueue and payload behavior;
- avoided production validation.

## Next Boundary

`server-py:workbench-refresh-status-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-groups-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` refresh-status handler
   - `tests/test_workbench_routes.py`
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Add refresh-status delegation to `WorkbenchReadApiRoutes`.
4. Update `_handle_api_workbench_refresh_status(...)` to delegate to `self._workbench_read_routes().refresh_status(...)`.
5. Add route-owner test and static Guard coverage.
6. Do not move SSE events or `_workbench_refresh_status_payload_for_scope(...)`.
7. Update state/queue/journal/next prompt, run targeted tests/docs/diff checks and commit/push.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move SSE events, refresh-status payload helpers or legacy `/api/workbench` SQL fallback in this slice.
