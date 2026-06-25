# server-py:workbench-read-route-owner-post-refresh-status-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-refresh-status-route-owner-extraction`
**Next boundary:** `server-py:workbench-events-stream-route-owner-extraction`

## Purpose

Audit remaining Workbench read-route `Application` surfaces after summary, groups and refresh-status route-owner extraction, then select the next narrow local boundary.

## Current Evidence

- `WorkbenchReadApiRoutes` now owns summary, groups and refresh-status facade delegation.
- `Application` still owns:
  - `GET /api/workbench/events` SSE response creation and stream lifecycle;
  - active stream registry helper methods;
  - refresh-status payload normalization used by SSE/App Health/runtime status paths;
  - legacy `GET /api/workbench` SQL fallback, refresh enqueue and payload building.
- Existing `tests/test_workbench_sql_runtime.py` covers Workbench SSE behavior:
  - refresh status event emission;
  - no-buffering headers and heartbeat;
  - polling path without Redis PubSub;
  - close cleanup releasing active stream slot.

## Classification

| Surface | Current owner | Classification | Decision |
| --- | --- | --- | --- |
| `GET /api/workbench/events` | `Application._handle_api_workbench_events(...)` | SSE stream route body/headers with explicit lifecycle ports | Safe next route-owner extraction |
| `_mark_workbench_events_stream_started/closed(...)` | `Application` active stream registry | lifecycle state helper | Keep as explicit ports for the next slice; move later only if it remains cohesive |
| `_workbench_refresh_status_payload_for_scope(...)` and normalization helpers | `Application` refresh-status/App Health/SSE support | shared status payload service candidate | Defer; do not mix with SSE route extraction |
| legacy `GET /api/workbench` | `_handle_api_workbench(...)`, SQL read model fallback, enqueue and payload builders | larger read-model gateway/service boundary | Defer to a dedicated implementation analysis |

## Selected Next Boundary

Select `server-py:workbench-events-stream-route-owner-extraction`.

The next slice should introduce an explicit SSE route owner with ports for:

- scope key resolution;
- refresh-status payload lookup;
- event-name mapping;
- SSE serialization;
- stream start/close lifecycle;
- sleep/delay injection for tests.

`Application` should keep top-level dispatch and may keep `Response` construction if the route owner returns body/headers/stream metadata, or delegate complete SSE response construction if tests prove the HTTP contract remains unchanged.

## Inputs

- HTTP query `month`.
- `scope_key_for_month` port.
- `status_payload_for_scope` port.
- `event_name_for_payload` port.
- `serialize_sse_event` port.
- `mark_stream_started` and `mark_stream_closed` ports.
- `sleep` port.

## Outputs

- SSE stream body yielding status events and heartbeat events.
- Existing headers:
  - `Content-Type: text/event-stream; charset=utf-8`;
  - `Cache-Control: no-cache, no-transform`;
  - `Connection: keep-alive`;
  - `X-Accel-Buffering: no`;
  - CORS headers already returned by the current endpoint.

## State And Events

The route owner may call explicit lifecycle ports to increment/decrement active stream counts. It must not write canonical facts, dirty scopes, outbox, read model readiness, cache, App Status or relation state.

## Tests

The implementation should preserve and rerun the existing SSE tests in `tests/test_workbench_sql_runtime.py`, plus add a focused route-owner or static Guard proving SSE stream construction no longer lives in `Application._handle_api_workbench_events(...)`.

## Out Of Scope

- Do not move refresh-status payload normalization in the same slice.
- Do not change event names or heartbeat payload shape.
- Do not switch to Redis PubSub.
- Do not move legacy `/api/workbench` SQL fallback or payload builder logic.
- Do not run production browser/admin/write validation.

## Completion Semantics

Row 410 closes as `analysis-closed`. Row 411 is the next local implementation row. No Workbench module/global closure is claimed.
