# server-py:workbench-live-payload-builder-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-live-oa-raw-payload-source-audit`
**Next boundary:** `server-py:workbench-oa-raw-payload-source-audit`

## Purpose

Move live-source Workbench raw payload merge orchestration out of `Application._build_live_workbench_row_payload(...)` while preserving OA source and retained all-OA behavior.

## Implementation

- Added `WorkbenchLivePayloadBuilder` in `backend/src/fin_ops_platform/services/workbench_live_payload_builder.py`.
- The builder owns:
  - live payload loading;
  - OA payload loading through the existing `_build_oa_workbench_row_payload` compatibility port;
  - live/OA merge;
  - serialization of the merged payload.
- `Application._build_live_workbench_row_payload(...)` now delegates to `self._workbench_live_payload_builder().build(month)`.
- `Application` remains the composition root and injects explicit callable dependencies.

## Inputs

- Month.
- Explicit callable ports for live payload load, OA payload load, merge and serialization.

## Outputs

- Serialized live-source Workbench raw payload.

## State And Events

The builder itself does not know HTTP, repositories, auth, queues, caches, persistence or read-model freshness. Existing side effects remain in the injected helper ports and are unchanged.

## Read Model/Freshness Contract

No read-model freshness semantics changed. `_build_oa_workbench_row_payload` remains the compatibility boundary for existing tests and callers. retained all-OA behavior remains deferred.

## Tests And Guards

- Added `tests/test_workbench_live_payload_builder.py`.
- Added static Guard coverage proving `_build_live_workbench_row_payload(...)` no longer owns live merge steps and the builder has no HTTP/write/runtime side-effect dependencies.

## Out Of Scope

- `_build_oa_workbench_row_payload(...)` remains in `Application`.
- Retained all-OA source behavior remains in `Application`.
- Canonical OA attachment promotion remains in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
