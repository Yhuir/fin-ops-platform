# server-py:workbench-live-oa-merge-helper-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-live-oa-merge-helper-audit`
**Next boundary:** `server-py:workbench-group-row-payload-helper-audit`

## Purpose

Move live/OA raw payload row merge and row-id dedupe out of `Application`.

## Implementation

- Added `WorkbenchLiveOaMergeHelper` in `backend/src/fin_ops_platform/services/workbench_live_oa_merge_helper.py`.
- The helper owns:
  - merging OA status into live payloads;
  - replacing live OA rows with OA raw rows;
  - appending only OA attachment invoice rows from OA payloads;
  - row-id dedupe with later rows winning.
- `Application._merge_live_workbench_with_oa_rows(...)` and `_dedupe_workbench_rows_by_id_preferring_last(...)` now delegate to the helper.
- `Application._merge_live_workbench_with_oa(...)` remains the grouped merge compatibility wrapper and still calls `_group_row_payload(...)`.

## Inputs

- Live payload dictionaries.
- OA payload dictionaries.
- Serialization port for row/payload values.

## Outputs

- Merged raw Workbench payload dictionaries.
- Deduped row lists.

## State And Events

The helper is pure and read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing Workbench live/OA flow still calls the same `Application` helper names, which now delegate to the helper.

## Tests And Guards

- Added `tests/test_workbench_live_oa_merge_helper.py`.
- Updated static Guard coverage proving `Application` no longer owns live/OA row merge or row-id dedupe details.

## Out Of Scope

- group row payload helper extraction remains deferred, including grouped merge boundaries.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
