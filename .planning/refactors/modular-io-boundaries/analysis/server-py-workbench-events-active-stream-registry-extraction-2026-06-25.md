# server-py:workbench-events-active-stream-registry-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-read-route-owner-post-events-audit`
**Next boundary:** `server-py:workbench-read-route-owner-post-stream-registry-audit`

## Purpose

Move Workbench SSE active stream count and lock management out of `Application` into a cohesive local owner, while preserving stream close cleanup behavior.

## Implementation

- Added `WorkbenchEventsActiveStreamRegistry` in `backend/src/fin_ops_platform/services/workbench_events_active_stream_registry.py`.
- Removed `Application` ownership of:
  - `_workbench_events_active_streams_lock`;
  - `_workbench_events_active_streams`;
  - `_mark_workbench_events_stream_started(...)`;
  - `_mark_workbench_events_stream_closed(...)`;
  - `_workbench_events_active_streams_registry(...)`.
- Added `Application._workbench_events_stream_registry(...)` as a composition-root accessor for the registry owner.
- Updated `_build_workbench_events_api_routes(...)` to inject `stream_registry.mark_started` and `stream_registry.mark_closed` into `WorkbenchEventsApiRoutes`.
- Updated the stream close cleanup test to assert the registry snapshot instead of the old `Application` dict.

## Inputs

- `scope_key` strings from `WorkbenchEventsApiRoutes`.

## Outputs

- `mark_started(scope_key)` increments process-local active stream count.
- `mark_closed(scope_key)` decrements or removes process-local active stream count.
- `snapshot()` provides a copy for local verification and diagnostics.

## State And Events

This owner is process-local diagnostic state only. It does not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or relation state.

## Read Model/Freshness Contract

No read model freshness semantics changed. Refresh-status payload normalization remains outside this slice and is still deferred.

## Tests And Guards

- Existing Workbench SSE tests still cover event emission, heartbeat/no-buffering headers, polling without Redis PubSub and stream close cleanup.
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_events_active_stream_registry_extraction_stays_local` guards:
  - old `Application` registry helpers stay removed;
  - the new registry owner has the expected methods;
  - route builder wiring uses `stream_registry.mark_started` / `mark_closed`;
  - the registry owner has no HTTP/response/read-model write dependencies.

## Out Of Scope

- Do not move refresh-status payload normalization in this slice.
- Do not change event names, heartbeat shape, SSE headers or polling behavior.
- Do not move legacy `/api/workbench` SQL fallback or payload builders.
- Do not run production browser/admin/write validation.

## Completion Semantics

This row may be marked `local-implementation-closed` after local SSE tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
