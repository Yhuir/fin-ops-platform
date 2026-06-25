# server-py:workbench-read-route-owner-post-normalizer-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-refresh-status-payload-normalizer-extraction`
**Selected next boundary:** `server-py:workbench-refresh-status-payload-provider-extraction`

## Purpose

Audit the remaining Workbench read/support surfaces after refresh-status payload normalization moved out of `Application`.

## Findings

- `WorkbenchReadApiRoutes` owns summary/groups/refresh-status HTTP request mapping.
- `WorkbenchEventsApiRoutes` owns SSE stream body/header construction.
- `WorkbenchEventsActiveStreamRegistry` owns active stream count/lock state.
- `WorkbenchRefreshStatusPayloadNormalizer` owns payload normalization and SSE event-name mapping.
- `Application._workbench_refresh_status_payload_for_scope(...)` still owned repository lookup, source freshness decoration and normalizer invocation for the SSE route.
- Legacy `/api/workbench` SQL fallback and payload builders remain app-owned and are broader than this refresh-status provider boundary.

## Decision

Select `server-py:workbench-refresh-status-payload-provider-extraction` as the next narrow local implementation boundary.

This keeps the next change small:

- move repository refresh-status lookup plus source freshness and normalization orchestration into an explicit provider;
- keep legacy `/api/workbench` SQL fallback/payload handling deferred;
- avoid production validation while local Workbench implementation gaps remain.

## Out Of Scope

- No production browser/admin/write validation.
- No mutation flow.
- No legacy `/api/workbench` payload builder migration.
- No Go/Fiber/worker implementation.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.
