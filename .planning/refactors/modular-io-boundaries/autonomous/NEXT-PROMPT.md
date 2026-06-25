# Next Prompt

Continue after `server-py:workbench-read-route-owner-post-events-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-read-route-owner-post-events-audit`.
- Row412 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-events-audit-2026-06-25.md`.
- Selected next local implementation boundary: `server-py:workbench-events-active-stream-registry-extraction`.
- Refresh-status payload normalization and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-read-route-owner-post-events-audit` is complete:

- audited remaining Workbench read/support surfaces after events route extraction;
- selected active stream registry extraction as the next narrow local boundary;
- deferred refresh-status payload normalization because it is shared by SSE/App Health/API status;
- deferred legacy `/api/workbench` SQL fallback/payload handling as a larger read-model gateway boundary;
- avoided production validation.

## Next Boundary

`server-py:workbench-events-active-stream-registry-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-events-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` active stream registry helpers and events route builder
   - `tests/test_workbench_sql_runtime.py` Workbench events tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Move active stream count/lock management out of `Application` into a cohesive owner.
4. Wire `WorkbenchEventsApiRoutes` through explicit `mark_started`/`mark_closed` ports from the new owner.
5. Preserve stream close cleanup behavior and update tests/static Guard.
6. Do not move refresh-status payload normalization or legacy `/api/workbench` SQL fallback.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move refresh-status payload normalization or legacy `/api/workbench` SQL fallback in this slice.
