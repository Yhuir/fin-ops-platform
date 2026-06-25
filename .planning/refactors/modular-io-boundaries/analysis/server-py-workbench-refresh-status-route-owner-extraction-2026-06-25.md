# server-py:workbench-refresh-status-route-owner-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-read-route-owner-post-groups-audit`
**Next boundary:** `server-py:workbench-read-route-owner-post-refresh-status-audit`

## Purpose

Move `GET /api/workbench/refresh-status` facade delegation out of `Application` and into `WorkbenchReadApiRoutes`, preserving the existing JSON response mapping and leaving SSE refresh-status payload helpers untouched.

## Implementation

- Added `WorkbenchReadApiRoutes.refresh_status(...)`.
- Updated `Application._handle_api_workbench_refresh_status(...)` to delegate to `self._workbench_read_routes().refresh_status(...)`.
- Extended Workbench route-owner unit coverage for refresh-status delegation.
- Extended the Workbench read route static Guard to ensure `Application` no longer calls `WorkbenchQueryFacade.refresh_status(...)` directly from the refresh-status handler.

## Inputs

- HTTP query `month`.
- Existing `WorkbenchQueryFacade` provider.

## Outputs

- `(HTTPStatus, payload)` route-owner result.
- Existing `Application._json_response(...)` envelope.

## State And Events

No canonical facts, dirty scopes, outbox events, readiness, cache, App Status, relation state or worker queue state are written by this route owner.

## Read Model/Freshness Contract

`WorkbenchQueryFacade.refresh_status(...)` remains the freshness/status owner. This slice only moves facade delegation behind the read route owner. `_workbench_refresh_status_payload_for_scope(...)`, `_normalize_workbench_refresh_status_payload(...)`, SSE heartbeat generation and App Health/status integrations remain in `Application` for later dedicated boundaries.

## Tests And Guards

- `tests/test_workbench_routes.py::WorkbenchReadApiRoutesTests::test_refresh_status_delegates_to_query_facade`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_groups_read_route_owner_extraction_stays_local`
- `tests/test_read_model_api_contract_harness.py` local API harness still covers `/api/workbench/refresh-status` through the default probe inventory when run broadly; this slice reruns the summary/groups-focused harness path that includes Workbench read endpoints.

## Out Of Scope

- Do not move SSE events in this slice.
- Do not move `_workbench_refresh_status_payload_for_scope(...)`, event-name mapping or active stream registry helpers.
- Do not move legacy `/api/workbench` SQL fallback, stale-source enqueue or payload builder paths.
- Do not run production browser/admin/write validation.

## Docs Impact

No API contract, product behavior, permission behavior or freshness semantics changed. The state-machine and analysis files record the internal route-owner movement; module docs remain unchanged.

## Completion Semantics

This row may be marked `local-implementation-closed` after local route-owner tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
