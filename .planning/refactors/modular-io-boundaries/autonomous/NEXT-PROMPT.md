# Next Prompt

Continue after `planning:post-no-oa-server-local-support-next-boundary-selection`.

## Current State

- Branch: `dev`.
- Last completed boundary: `planning:post-no-oa-server-local-support-next-boundary-selection`.
- Row406 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/planning-post-no-oa-server-local-support-next-boundary-selection-2026-06-25.md`.
- Selected next local implementation boundary: `server-py:workbench-groups-read-route-owner-extraction`.
- Workbench group detail is already route-owned, but summary/groups list validation and facade mapping still live in `Application`.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`planning:post-no-oa-server-local-support-next-boundary-selection` is complete:

- read current state/queue and Workbench module docs;
- inspected `routes_workbench.py` and residual Workbench `server.py` read route handlers;
- identified `GET /api/workbench/summary` and `GET /api/workbench/groups` as the next narrow local route-owner gap;
- explicitly deferred `GET /api/workbench/events` and `GET /api/workbench/refresh-status` to later slices;
- avoided production validation.

## Next Boundary

`server-py:workbench-groups-read-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/planning-post-no-oa-server-local-support-next-boundary-selection-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` Workbench summary/groups handlers
   - `tests/test_workbench_routes.py`
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Write the implementation analysis for `server-py:workbench-groups-read-route-owner-extraction`.
4. Move Workbench summary/groups read validation and facade mapping into `routes_workbench.py` behind explicit ports.
5. Keep `Application` responsible for top-level route dispatch, JSON response construction and Workbench metrics.
6. Add local route-owner tests and a static Guard preventing group-list validation from returning to `Application`.
7. Update state/queue/journal/next prompt, run targeted tests/docs/diff checks, commit/push.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move SSE events or controlled production browser/admin/write evidence in this slice.
