# server-py:workbench-group-detail-route-owner-extraction

**Date:** 2026-06-24
**Status:** implementation-closed
**Previous boundary:** `server-py:workbench-group-detail-route-owner-audit`
**Next boundary:** controller-owned queue/state accounting

## Goal

Extract `GET /api/workbench/groups/detail` HTTP validation and facade response mapping from `Application` behind an explicit read-only route owner while preserving response shape, status codes, freshness proof, read model refresh enqueue behavior and relation no-write behavior.

This is a narrow server ownership implementation slice. It does not change Workbench group detail business semantics, active generation publishing, freshness/source-version validation, relation writes, frontend behavior, production state, Go/Fiber or Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-group-detail-route-owner-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-row-detail-route-owner-extraction.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `tests/test_workbench_query_facade.py`
- `tests/test_workbench_sql_runtime.py`

## Change Summary

- Added `WorkbenchGroupDetailApiRoutes` in `routes_workbench.py`.
- Moved group detail route-local validation into `WorkbenchGroupDetailApiRoutes.get_detail(...)`:
  - defaults missing `month` to `all`;
  - trims and validates `zone`;
  - trims and requires `group_id`;
  - delegates to `WorkbenchQueryFacade.group_detail(...)`;
  - returns the facade status code and payload unchanged.
- `Application._handle_api_workbench_group_detail(...)` is now a thin wrapper that calls `_workbench_group_detail_routes().get_detail(...)` and serializes the returned status/payload as JSON.
- `Application` now only assembles the explicit route-owner dependency through `_build_workbench_group_detail_api_routes(...)`.
- Added focused route-owner tests in `tests/test_workbench_routes.py`.

## Preserved Contract

- Invalid `zone` still returns `400 {"error": "invalid_workbench_zone", "message": "zone must be open or paired."}`.
- Missing or blank `group_id` still returns `400 {"error": "invalid_workbench_group_detail_request", "message": "group_id is required."}`.
- Valid requests still call `WorkbenchQueryFacade.group_detail(current_month, zone=normalized_zone, group_id=normalized_group_id)`.
- `WorkbenchQueryFacade.group_detail(...)` still owns active generation `source_versions`, `read_model_status`, `read_model_version`, stale refresh enqueue and stale/not-found mapping.
- The new route owner is read-only; it does not import relation command services, enqueue read model refresh directly, write dirty scopes/outbox/readiness, mutate Redis cache, or mutate canonical facts.

## Non-Goals

- Do not change group detail payload fields, frontend drawer behavior, active generation query behavior or freshness status semantics.
- Do not change Workbench row detail, groups page, refresh status, settings, matching worker, read model persistence/enqueue, legacy Workbench actions, modern Workbench action behavior or relation writes.
- Do not edit controller-owned `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` or master prompt files in this worker slice.
- Do not implement Go, Go Fiber or Go Worker.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no relation state, matching, amount or business rule changed.
2. Service-layer tests: not applicable; no service behavior changed. The route owner depends on the existing facade boundary.
3. API contract tests: covered by new focused route-owner tests for status codes, validation payloads, normalized delegation and facade payload/status passthrough; existing facade/repository tests cover freshness payloads.
4. Read model/cache/background job tests: covered by existing group detail facade and SQL repository tests; no worker/cache behavior changed.
5. Frontend component and interaction tests: not applicable; API shape and frontend drawer behavior are unchanged.
6. End-to-end business-flow integration tests: not required for this route-owner extraction; no cross-module write/read flow changed.
7. Existing feature regression tests: covered by existing group detail freshness tests plus the focused route-owner tests.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_routes tests.test_workbench_query_facade.WorkbenchQueryFacadeTests.test_group_detail_stale_source_versions_do_not_return_stale_group tests.test_workbench_query_facade.WorkbenchQueryFacadeTests.test_group_detail_refreshing_status_does_not_return_stale_group tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_group_detail_includes_active_generation_freshness_contract -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench.py backend/src/fin_ops_platform/app/server.py tests/test_workbench_routes.py
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- This worker slice closes implementation for `server-py:workbench-group-detail-route-owner-extraction`.
- Controller-owned queue/state/master prompt files were intentionally not edited. The controller should advance row 217 and select any adjacent next route-owner boundary.
