# server-py:workbench-cache-read-payload-helper-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-cache-read-payload-helper-audit`
**Next boundary:** `server-py:workbench-oa-invoice-offset-rebuild-helper-audit`

## Purpose

Move Workbench cached/read payload readiness decisions out of `Application`.

## Implementation

- Added `WorkbenchCacheReadPayloadHelper` in `backend/src/fin_ops_platform/services/workbench_cache_read_payload_helper.py`.
- The helper owns:
  - cached payload use gate;
  - persist/fallback gates;
  - Mongo vs non-Mongo OA status readiness semantics;
  - schema/hash/parser/rules version checks;
  - cached OA summary gate.
- `Application._can_use_cached_workbench_payload(...)`, `_can_persist_workbench_payload(...)`, `_can_fallback_to_stale_workbench_payload(...)` and `_oa_status_is_ready_for_cache(...)` now delegate to the helper.
- `Application` remains the composition root and injects Mongo adapter detection, OA invoice offset rebuild detection, candidate hash and version constants as explicit dependencies.

## Inputs

- Cached/grouped Workbench payload dictionaries.
- Explicit ports for Mongo adapter detection, OA invoice offset rebuild, candidate hash, parser version and schema/rule versions.

## Outputs

- Boolean cache use, persist, fallback and OA status readiness decisions.

## State And Events

The helper is read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing read/persist/fallback flows still call the same `Application` helper names, which now delegate to the helper.

## Tests And Guards

- Added `tests/test_workbench_cache_read_payload_helper.py`.
- Updated static Guard coverage proving `Application` no longer owns cache/read payload readiness details.

## Out Of Scope

- OA invoice offset rebuild helper extraction remains deferred to `server-py:workbench-oa-invoice-offset-rebuild-helper-audit`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
