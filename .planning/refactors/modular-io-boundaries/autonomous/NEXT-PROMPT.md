# Next Prompt

Continue after `server-py:workbench-read-route-owner-post-stream-registry-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-read-route-owner-post-stream-registry-audit`.
- Row414 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-stream-registry-audit-2026-06-25.md`.
- Selected next local implementation boundary: `server-py:workbench-refresh-status-payload-normalizer-extraction`.
- Repository status lookup and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-read-route-owner-post-stream-registry-audit` is complete:

- audited remaining Workbench read/support surfaces after active stream registry extraction;
- selected refresh-status payload normalization/event-name mapping extraction as the next narrow local boundary;
- deferred repository status lookup because it has repository/source-version dependencies;
- deferred legacy `/api/workbench` SQL fallback/payload handling as a larger read-model gateway boundary;
- avoided production validation.

## Next Boundary

`server-py:workbench-refresh-status-payload-normalizer-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-read-route-owner-post-stream-registry-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` Workbench refresh-status/SSE tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Move refresh-status payload normalization and event-name mapping into a pure owner.
4. Wire `WorkbenchQueryFacade` and `WorkbenchEventsApiRoutes` through the new owner.
5. Preserve refresh-status API and SSE behavior with tests/static Guard.
6. Do not move repository status lookup or legacy `/api/workbench` SQL fallback.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move repository status lookup or legacy `/api/workbench` SQL fallback in this slice.
