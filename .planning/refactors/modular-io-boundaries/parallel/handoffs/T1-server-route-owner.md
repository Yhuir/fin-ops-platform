# T1 server route-owner handoff

**Date:** 2026-06-24
**Branch:** `dev`
**Worker scope:** server route-owner extraction without controller-only state edits

## Completed Boundary

`server-py:workbench-group-detail-route-owner-extraction` is implemented.

## Files Changed

- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_routes.py`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-group-detail-route-owner-extraction.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `.planning/refactors/modular-io-boundaries/parallel/handoffs/T1-server-route-owner.md`

## Implementation Facts

- Added `WorkbenchGroupDetailApiRoutes` as the read-only route owner for `GET /api/workbench/groups/detail`.
- `WorkbenchGroupDetailApiRoutes.get_detail(...)` owns HTTP-level validation and mapping:
  - `month` defaults to `all`;
  - `zone` is trimmed and must be `open` or `paired`;
  - `group_id` is trimmed and required;
  - valid requests delegate to `WorkbenchQueryFacade.group_detail(...)`;
  - facade status code and payload pass through unchanged.
- `Application._handle_api_workbench_group_detail(...)` is now a thin JSON wrapper around `_workbench_group_detail_routes().get_detail(...)`.
- Freshness/source-version/read-model-status proof stays in `WorkbenchQueryFacade.group_detail(...)`.
- No relation writes, dirty scope writes, outbox writes, Redis cache writes, readiness mutation, active generation mutation, Go/Fiber or Go Worker changes were made.

## Tests Added

- `tests/test_workbench_routes.py::WorkbenchGroupDetailApiRoutesTests`
  - validation error payload for invalid zone;
  - validation error payload for missing group id;
  - normalized valid delegation and facade status/payload passthrough.

## Controller-Owned Follow-Up

Per worker prompt, this slice did not edit:

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- master prompt files

The controller should record `server-py:workbench-group-detail-route-owner-extraction` as implementation-closed and select the next adjacent server route-owner boundary, if any, that stays within the same route-owner file family and does not require controller-only state edits.
