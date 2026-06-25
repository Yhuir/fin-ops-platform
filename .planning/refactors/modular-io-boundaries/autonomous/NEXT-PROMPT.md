# Next Prompt

Continue after `server-py:workbench-refresh-status-route-owner-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-refresh-status-route-owner-extraction`.
- Row409 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-route-owner-extraction-2026-06-25.md`.
- `WorkbenchReadApiRoutes` now owns summary, groups and refresh-status facade delegation.
- SSE events, refresh-status payload helpers and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-refresh-status-route-owner-extraction` is complete:

- added `WorkbenchReadApiRoutes.refresh_status(...)`;
- moved `GET /api/workbench/refresh-status` facade delegation out of `Application`;
- preserved `Application` dispatch and JSON response mapping;
- left SSE refresh-status payload helpers untouched;
- added route-owner test and static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-read-route-owner-post-refresh-status-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-route-owner-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read handlers
   - `tests/test_workbench_routes.py`
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read-route `Application` surfaces:
   - `/api/workbench/events` SSE lifecycle;
   - `_workbench_refresh_status_payload_for_scope(...)` and normalization helpers;
   - legacy `/api/workbench` SQL fallback and payload builder path.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement in a bounded slice with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move SSE events, refresh-status payload helpers or legacy `/api/workbench` SQL fallback unless the audit proves a narrow local split with lifecycle/freshness tests.
