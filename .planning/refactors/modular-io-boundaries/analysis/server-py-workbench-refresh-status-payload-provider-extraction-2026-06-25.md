# server-py:workbench-refresh-status-payload-provider-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-read-route-owner-post-normalizer-audit`
**Next boundary:** `server-py:workbench-legacy-api-sql-fallback-audit`

## Purpose

Move Workbench refresh-status repository status lookup orchestration out of `Application` into an explicit read-only provider while preserving refresh-status API and SSE behavior.

## Implementation

- Added `WorkbenchRefreshStatusPayloadProvider` in `backend/src/fin_ops_platform/services/workbench_refresh_status_payload_provider.py`.
- The provider owns:
  - resolving the repository through an explicit `repository_provider` port;
  - calling `get_workbench_refresh_status(scope_key=...)` when available;
  - applying source freshness through an explicit `source_freshness` port;
  - delegating canonical payload shaping to `WorkbenchRefreshStatusPayloadNormalizer`.
- Wired `WorkbenchEventsApiRoutes` through `status_payload_provider.payload_for_scope`.
- Removed `Application._workbench_refresh_status_payload_for_scope(...)`.

## Inputs

- `scope_key`.
- Workbench SQL read repository provider.
- Source freshness function.
- `WorkbenchRefreshStatusPayloadNormalizer`.

## Outputs

- Normalized Workbench refresh-status payload for SSE route consumption.

## State And Events

The provider is read-only. It does not write dirty scopes, enqueue outbox events, mutate readiness, write cache, persist state, or construct HTTP responses.

## Read Model/Freshness Contract

Refresh-status API behavior remains owned by `WorkbenchQueryFacade`. SSE behavior now uses the provider with the same source freshness and normalization contract as the previous app helper.

## Tests And Guards

- Added `tests/test_workbench_refresh_status_payload_provider.py`.
- Preserved Workbench SSE tests:
  - `test_workbench_events_stream_emits_refresh_status_event`
  - `test_workbench_events_stream_exposes_no_buffering_headers_and_heartbeat`
  - `test_workbench_events_stream_maps_statuses_without_redis_pubsub`
  - `test_workbench_events_stream_close_releases_active_stream_slot`
- Preserved refresh-status API normalization tests.
- Added static Guard coverage proving `Application` no longer owns `_workbench_refresh_status_payload_for_scope(...)` and the provider has no HTTP/write/runtime side-effect dependencies.

## Out Of Scope

- legacy `/api/workbench` SQL fallback and payload builders remain deferred.
- Repository implementation SQL remains unchanged.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
