# server-py:workbench-read-route-owner-post-stream-registry-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-events-active-stream-registry-extraction`
**Next boundary:** `server-py:workbench-refresh-status-payload-normalizer-extraction`

## Purpose

Audit remaining Workbench read/support surfaces after active stream registry extraction and select the next narrow local implementation boundary.

## Current Evidence

- Route-owner extraction is complete for Workbench summary, groups, refresh-status and SSE stream construction.
- `WorkbenchEventsActiveStreamRegistry` owns process-local SSE active stream count state.
- Remaining `Application` Workbench read/support surfaces include:
  - `_workbench_refresh_status_payload_for_scope(...)`;
  - `_normalize_workbench_refresh_status_payload(...)`;
  - `_workbench_refresh_status_event_name(...)`;
  - legacy `/api/workbench` SQL fallback and payload building.

## Classification

| Surface | Current owner | Classification | Decision |
| --- | --- | --- | --- |
| `_normalize_workbench_refresh_status_payload(...)` | `Application` static helper injected into `WorkbenchQueryFacade` and used by SSE status payload lookup | pure payload normalization and retryability/status mapping | Safe next extraction |
| `_workbench_refresh_status_event_name(...)` | `Application` static helper injected into `WorkbenchEventsApiRoutes` | pure status-to-SSE-event mapping | Move with payload normalizer |
| `_workbench_refresh_status_payload_for_scope(...)` | `Application` repository lookup plus source freshness and normalization | status payload provider with repository/source-version dependencies | Keep as composition/support wrapper for now; may delegate to normalizer |
| legacy `/api/workbench` SQL fallback/payload path | `Application` | larger read-model gateway, enqueue and legacy payload boundary | Defer to dedicated implementation analysis |

## Selected Next Boundary

Select `server-py:workbench-refresh-status-payload-normalizer-extraction`.

The next slice should move refresh-status payload normalization and event-name mapping into a cohesive service/owner. `Application` should instantiate or lazily access that owner, pass `normalize` into `WorkbenchQueryFacade`, pass `event_name` into `WorkbenchEventsApiRoutes`, and use it from `_workbench_refresh_status_payload_for_scope(...)`.

## Inputs

- Raw refresh-status payload dict.
- `scope_key`.
- `fallback_status`.

## Outputs

- Normalized payload with:
  - `scope_key`;
  - canonical `read_model_status`;
  - `generated_at`;
  - generation ids;
  - `read_model_version`;
  - `dirty_scopes`;
  - `running_scopes`;
  - counts and worker lag;
  - `last_error`;
  - `retryable`.
- SSE event name for normalized status.

## State And Events

The owner must be pure and stateless. It must not read repositories, write canonical facts, dirty scopes, outbox events, readiness, cache, App Status or relation state.

## Tests

Preserve existing Workbench refresh-status/SSE tests in `tests/test_workbench_sql_runtime.py`, especially:

- `test_workbench_refresh_status_api_normalizes_failed_dirty_scope`
- `test_workbench_refresh_status_api_treats_requeued_failed_scope_as_refreshing`
- `test_workbench_events_stream_maps_statuses_without_redis_pubsub`

Add direct unit or static Guard coverage proving the normalizer owner has no HTTP/repository/write dependencies and `Application` no longer owns the static normalizer/event-name helpers.

## Out Of Scope

- Do not move repository status lookup in this slice.
- Do not move legacy `/api/workbench` SQL fallback or payload builders.
- Do not change read-model status semantics, event names or heartbeat shape.
- Do not run production browser/admin/write validation.

## Completion Semantics

Row 414 closes as `analysis-closed`. Row 415 is the next local implementation row. No Workbench module/global closure is claimed.
