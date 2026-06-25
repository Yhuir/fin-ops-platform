# server-py:workbench-events-stream-route-owner-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-read-route-owner-post-refresh-status-audit`
**Next boundary:** `server-py:workbench-read-route-owner-post-events-audit`

## Purpose

Move `GET /api/workbench/events` SSE stream body/header mapping out of `Application` and into an explicit route owner, while preserving stream lifecycle cleanup, heartbeat shape, no-buffering headers and polling-without-Redis behavior.

## Implementation

- Added `WorkbenchEventsApiRoutes` in `routes_workbench.py`.
- `WorkbenchEventsApiRoutes.events(...)` owns:
  - month-to-scope resolution through an injected port;
  - status payload lookup through an injected port;
  - status event-name mapping through an injected port;
  - SSE event serialization through an injected port;
  - stream start/close lifecycle through injected ports;
  - heartbeat event payload shape;
  - SSE/no-buffering/CORS headers;
  - injected sleep for the polling loop.
- Updated `Application._handle_api_workbench_events(...)` to delegate stream construction and only wrap the route owner result into `Response`.
- Kept `_workbench_refresh_status_payload_for_scope(...)`, `_normalize_workbench_refresh_status_payload(...)`, event-name mapping and active stream registry helpers in `Application` as explicit ports for this slice.

## Inputs

- HTTP query `month`.
- `scope_key_for_month`.
- `status_payload_for_scope`.
- `event_name_for_payload`.
- `serialize_sse_event`.
- `mark_stream_started`.
- `mark_stream_closed`.
- `sleep_seconds`.

## Outputs

- Streaming body yielding Workbench read-model status events and heartbeat events.
- Existing headers:
  - `Content-Type: text/event-stream; charset=utf-8`;
  - `Cache-Control: no-cache, no-transform`;
  - `Connection: keep-alive`;
  - `X-Accel-Buffering: no`;
  - existing CORS headers.
- Existing `Application` `Response` wrapper with `stream=True`.

## State And Events

The route owner only calls explicit lifecycle ports to track active stream counts. It does not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or relation state.

## Read Model/Freshness Contract

Refresh-status payload normalization and source-version freshness remain in existing `Application` support methods for this slice. The SSE route owner consumes the already-normalized payload through a port and does not change status semantics.

## Tests And Guards

- Existing Workbench SSE tests in `tests/test_workbench_sql_runtime.py` cover:
  - refresh status event emission;
  - no-buffering headers and heartbeat;
  - polling path without Redis PubSub;
  - stream close cleanup releasing active stream slot.
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_events_stream_route_owner_extraction_stays_local` guards that stream body/header mapping moved to `WorkbenchEventsApiRoutes`, `Application` delegates, and explicit ports remain visible.

## Out Of Scope

- Do not move `_workbench_refresh_status_payload_for_scope(...)` or `_normalize_workbench_refresh_status_payload(...)`.
- Do not change event names or heartbeat payload shape.
- Do not switch to Redis PubSub.
- Do not move legacy `/api/workbench` SQL fallback or payload builder logic.
- Do not run production browser/admin/write validation.

## Completion Semantics

This row may be marked `local-implementation-closed` after local SSE tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
