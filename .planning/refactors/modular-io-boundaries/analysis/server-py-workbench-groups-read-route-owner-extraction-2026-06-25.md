# server-py:workbench-groups-read-route-owner-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `planning:post-no-oa-server-local-support-next-boundary-selection`
**Next boundary:** `server-py:workbench-read-route-owner-post-groups-audit`

## Purpose

Move Workbench summary and grouped-list read HTTP validation/mapping out of `Application` and into an explicit route owner, without changing Workbench active generation, freshness, source-version, cache or write behavior.

## Implementation

- Added `WorkbenchReadApiRoutes` in `backend/src/fin_ops_platform/app/routes_workbench.py`.
- Moved read-only route mapping for:
  - `GET /api/workbench/summary`;
  - `GET /api/workbench/groups`.
- `WorkbenchReadApiRoutes` now owns:
  - group `zone` validation;
  - `search_mode` normalization;
  - `detail_level` normalization;
  - `search_by_pane`, `column_filters` and `time_filters` JSON object parsing and stable normalization;
  - delegation to `WorkbenchQueryFacade.summary(...)` and `WorkbenchQueryFacade.groups(...)`.
- `Application` now keeps only top-level route dispatch, `Response` construction, dependency assembly and existing Workbench API metrics for these endpoints.
- Removed the migrated group-list normalizer helpers from `server.py`.

## Inputs

- HTTP query values from `Application.handle_request(...)`.
- `WorkbenchQueryFacade` provider injected by `Application._build_workbench_read_api_routes(...)`.
- Existing Workbench group normalizer functions from `workbench_groups_page_cache`.

## Outputs

- `(HTTPStatus, payload)` from `WorkbenchReadApiRoutes.summary(...)` and `.groups(...)`.
- Existing JSON `Response` envelopes produced by `Application._json_response(...)`.
- Existing metric emission in the top-level dispatch for `/api/workbench/summary` and `/api/workbench/groups`.

## State And Events

No write-side state is changed. This route owner does not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or relation state.

## Read Model/Freshness Contract

Read model freshness remains owned by `WorkbenchQueryFacade` and downstream Workbench read model repository/gateway code. This slice only moves request validation and facade parameter mapping. It does not alter `read_model_status`, source-version proof, Redis caching, active generation publish or operation barrier semantics.

## Permissions

The existing `Application.handle_request(...)` authentication and session path remains unchanged. No new permission logic is introduced.

## Tests And Guards

- `tests/test_workbench_routes.py` now covers summary delegation, groups query normalization, invalid zone rejection and invalid JSON rejection.
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_groups_read_route_owner_extraction_stays_local` guards:
  - `WorkbenchReadApiRoutes` owns summary/groups mapping;
  - the `server.py` group handler no longer owns group query normalizers or direct facade groups calls;
  - the route owner remains read-only and has no write/runtime side effects.

## Out Of Scope

- `GET /api/workbench/events` / SSE events remain in `Application` because it owns SSE stream registry, heartbeat and lifecycle cleanup.
- `GET /api/workbench/refresh-status` remains in `Application` for a later narrow slice.
- `GET /api/workbench` legacy/full payload path remains unchanged.
- No production browser/admin/write evidence is collected in this local implementation slice.

## Docs Impact

No long-term product/API behavior changed. Module docs remain applicable; this analysis, queue and state-machine update record the internal route-owner refactor evidence.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
