# server-py:workbench-read-route-owner-post-events-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-events-stream-route-owner-extraction`
**Next boundary:** `server-py:workbench-events-active-stream-registry-extraction`

## Purpose

Audit remaining Workbench read/support surfaces after summary, groups, refresh-status and SSE stream route-owner extraction, then select the next narrow local implementation boundary.

## Current Evidence

- `WorkbenchReadApiRoutes` owns Workbench summary, groups and refresh-status facade delegation.
- `WorkbenchEventsApiRoutes` owns SSE stream body/header mapping and receives explicit lifecycle ports from `Application`.
- `Application` still owns:
  - `_mark_workbench_events_stream_started(...)`;
  - `_mark_workbench_events_stream_closed(...)`;
  - `_workbench_events_active_streams_registry(...)`;
  - `_workbench_refresh_status_payload_for_scope(...)`;
  - `_normalize_workbench_refresh_status_payload(...)`;
  - `_workbench_refresh_status_event_name(...)`;
  - legacy `/api/workbench` SQL fallback and payload building.

## Classification

| Surface | Current owner | Classification | Decision |
| --- | --- | --- | --- |
| Workbench events active stream registry helpers | `Application` | in-memory lifecycle state for SSE route owner | Safe next extraction |
| Refresh-status payload lookup/normalization | `Application` plus `WorkbenchQueryFacade` injection | shared status/freshness payload support for SSE, App Health and API status | Defer to dedicated status payload service analysis |
| Refresh-status event-name mapping | `Application` static helper | tiny status mapping used by SSE route owner | Can remain port for now or move with status payload service |
| legacy `/api/workbench` SQL fallback/payload path | `Application` | larger SQL read-model gateway, refresh enqueue and legacy payload behavior | Defer to dedicated implementation analysis with freshness tests |

## Selected Next Boundary

Select `server-py:workbench-events-active-stream-registry-extraction`.

The next slice should move active stream count/lock management out of `Application` into a cohesive local owner. `Application` should instantiate the owner and pass its `mark_started` / `mark_closed` methods into `WorkbenchEventsApiRoutes`.

## Inputs

- `scope_key` strings from the SSE route owner.
- Optional lock object or internally-owned lock.

## Outputs

- Active stream count increments on stream start.
- Active stream count decrements or removes scope on stream close.
- Test-visible snapshot/count access for local verification.

## State And Events

This is process-local in-memory diagnostic state only. The owner must not write canonical facts, dirty scopes, outbox, read model readiness, cache, App Status or relation state.

## Tests

The implementation should preserve:

- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_events_stream_close_releases_active_stream_slot`
- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_events_stream_emits_refresh_status_event`
- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_events_stream_exposes_no_buffering_headers_and_heartbeat`
- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_events_stream_maps_statuses_without_redis_pubsub`

Add or update static Guard coverage so `Application` no longer owns active stream registry helper methods after extraction.

## Out Of Scope

- Do not move refresh-status payload normalization in this slice.
- Do not change event names, heartbeat shape, SSE headers or polling behavior.
- Do not move legacy `/api/workbench` SQL fallback or payload builders.
- Do not run production browser/admin/write validation.

## Completion Semantics

Row 412 closes as `analysis-closed`. Row 413 is the next local implementation row. No Workbench module/global closure is claimed.
