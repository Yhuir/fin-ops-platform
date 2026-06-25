# Next Prompt

Continue after `server-py:workbench-groups-read-route-owner-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-groups-read-route-owner-extraction`.
- Row407 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-groups-read-route-owner-extraction-2026-06-25.md`.
- `WorkbenchReadApiRoutes` now owns summary/groups read validation and facade parameter mapping.
- `Application` keeps Workbench dispatch, response construction and API metrics.
- SSE events, refresh-status and legacy `/api/workbench` payload handling remain to be audited.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-groups-read-route-owner-extraction` is complete:

- added `WorkbenchReadApiRoutes`;
- moved `GET /api/workbench/summary` and `GET /api/workbench/groups` read validation/facade mapping out of `Application`;
- removed migrated group-list normalizer helpers from `server.py`;
- added `tests/test_workbench_routes.py` coverage for summary/groups route owner;
- added `test_workbench_groups_read_route_owner_extraction_stays_local` static Guard;
- confirmed the local API contract harness still covers `/api/workbench/summary` and `/api/workbench/groups`;
- avoided production validation.

## Next Boundary

`server-py:workbench-read-route-owner-post-groups-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-groups-read-route-owner-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read handlers
   - `tests/test_workbench_routes.py`
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read-route `Application` surfaces after summary/groups extraction:
   - `/api/workbench/refresh-status`;
   - `/api/workbench/events`;
   - legacy `/api/workbench` payload and SQL read-model fallback helpers.
4. Select the next narrow local implementation or guard boundary.
5. If a safe implementation slice exists, write analysis first, implement, test, update guards/state and commit/push.
6. If only audit is safe, write the audit, update state/queue/journal/next prompt, run docs/diff checks and commit/push.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move SSE events unless the audit proves a narrow route-owner split can preserve stream lifecycle cleanup.
