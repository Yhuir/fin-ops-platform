# server-py:workbench-read-route-owner-post-groups-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-groups-read-route-owner-extraction`
**Next boundary:** `server-py:workbench-refresh-status-route-owner-extraction`

## Purpose

Audit remaining Workbench read-route `Application` surfaces after summary/groups extraction and select the next narrow local boundary without starting production validation.

## Current Evidence

- `WorkbenchReadApiRoutes` now owns `GET /api/workbench/summary` and `GET /api/workbench/groups` request validation/facade mapping.
- `Application` still owns three read-route areas:
  - `GET /api/workbench/refresh-status` via `_handle_api_workbench_refresh_status(...)`;
  - `GET /api/workbench/events` via `_handle_api_workbench_events(...)` plus active stream registry and cleanup helpers;
  - legacy `GET /api/workbench` via `_handle_api_workbench(...)` and `_handle_api_workbench_from_sql_read_model(...)`.
- Tests already exercise these remaining areas in `tests/test_workbench_sql_runtime.py`, including refresh-status and SSE event behavior.

## Classification

| Surface | Current owner | Classification | Decision |
| --- | --- | --- | --- |
| `GET /api/workbench/refresh-status` | `Application._handle_api_workbench_refresh_status(...)` | thin facade delegate and JSON mapping | Safe next route-owner extraction |
| `GET /api/workbench/events` | `Application._handle_api_workbench_events(...)`, stream registry helpers and refresh-status payload helpers | SSE lifecycle and long-running stream boundary | Defer to a dedicated SSE route/service boundary |
| `GET /api/workbench` | `Application._handle_api_workbench(...)` and `_handle_api_workbench_from_sql_read_model(...)` | legacy top-level payload, SQL fallback, refresh enqueue, source-version stale handling | Defer to a larger read-model gateway/service boundary |

## Selected Next Boundary

Select `server-py:workbench-refresh-status-route-owner-extraction`.

This slice should add refresh-status handling to `WorkbenchReadApiRoutes`, delegate to `WorkbenchQueryFacade.refresh_status(...)`, and leave `Application` responsible for response construction and top-level dispatch.

## Inputs

- HTTP query `month`.
- Existing `WorkbenchQueryFacade` provider.

## Outputs

- `(HTTPStatus, payload)` refresh-status route-owner result.
- Existing JSON response shape from `Application._json_response(...)`.

## State And Events

No write state, dirty-scope mutation, outbox enqueue, readiness write, cache write, App Status write or relation mutation should be introduced. `WorkbenchQueryFacade.refresh_status(...)` remains the freshness/status owner.

## Tests

Targeted implementation tests should extend `tests/test_workbench_routes.py` for refresh-status delegation and static Guard coverage for the removed direct `Application` facade call. Existing `tests/test_workbench_sql_runtime.py` refresh-status tests can be used if the implementation changes response behavior; otherwise the route-owner and API contract harness coverage should be sufficient for the local boundary.

## Out Of Scope

- Do not move SSE events in this slice.
- Do not move `_workbench_refresh_status_payload_for_scope(...)` or `_normalize_workbench_refresh_status_payload(...)`; those serve SSE and App Health/runtime status code paths.
- Do not move legacy `/api/workbench` SQL fallback or refresh enqueue handling.
- Do not run production browser/admin/write validation.

## Completion Semantics

Row 408 closes as `analysis-closed`. Row 409 is the next local implementation row. No Workbench module/global closure is claimed.
