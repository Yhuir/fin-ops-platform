# server-py:workbench-refresh-status-payload-normalizer-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-read-route-owner-post-stream-registry-audit`
**Next boundary:** `server-py:workbench-read-route-owner-post-normalizer-audit`

## Purpose

Move Workbench refresh-status payload normalization and status-to-SSE-event mapping out of `Application` into a pure owner, while preserving refresh-status API and SSE behavior.

## Implementation

- Added `WorkbenchRefreshStatusPayloadNormalizer` in `backend/src/fin_ops_platform/services/workbench_refresh_status_payload.py`.
- Moved canonical `read_model_status`, `last_error`, `read_model_version`, retryability and status payload field normalization out of `Application`.
- Moved SSE event-name mapping out of `Application`.
- Wired `WorkbenchQueryFacade` through `WorkbenchRefreshStatusPayloadNormalizer.normalize`.
- Wired `WorkbenchEventsApiRoutes` through `WorkbenchRefreshStatusPayloadNormalizer.event_name`.
- Updated `_workbench_refresh_status_payload_for_scope(...)` to delegate normalization to the new owner.
- Removed `Application` ownership of `_normalize_workbench_refresh_status_payload(...)` and `_workbench_refresh_status_event_name(...)`.

## Inputs

- Raw refresh-status payload dict.
- `scope_key`.
- `fallback_status`.

## Outputs

- Normalized status payload.
- SSE event name for canonical read-model status.

## State And Events

The normalizer is pure/stateless. It does not read repositories, write canonical facts, dirty scopes, outbox, read model readiness, cache, App Status or relation state.

## Read Model/Freshness Contract

No refresh-status semantics changed. Existing Workbench refresh-status API and SSE tests still cover failed dirty scope, requeued failed scope, event-name mapping, heartbeat and close cleanup behavior.

## Tests And Guards

- Added `tests/test_workbench_refresh_status_payload.py`.
- Preserved Workbench refresh-status API tests:
  - `test_workbench_refresh_status_api_normalizes_failed_dirty_scope`
  - `test_workbench_refresh_status_api_treats_requeued_failed_scope_as_refreshing`
- Preserved Workbench SSE status mapping tests.
- Added static Guard coverage proving `Application` no longer owns the refresh-status normalizer/event-name helper and the owner has no HTTP/repository/write dependencies.

## Out Of Scope

- Repository status lookup remains in `_workbench_refresh_status_payload_for_scope(...)`.
- legacy `/api/workbench` SQL fallback and payload builders remain deferred.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
