# server-py:workbench-group-row-payload-helper-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-group-row-payload-helper-audit`
**Next boundary:** `server-py:workbench-cache-read-payload-helper-audit`

## Purpose

Move raw-to-grouped Workbench payload behavior out of `Application`.

## Implementation

- Added `WorkbenchGroupRowPayloadHelper` in `backend/src/fin_ops_platform/services/workbench_group_row_payload_helper.py`.
- The helper owns:
  - paired/open section extraction;
  - ignored-row filtering;
  - grouping service invocation;
  - OA status serialization/carry-over.
- `Application._group_row_payload(...)` now delegates to the helper with explicit `WorkbenchCandidateGroupingService` and serialization dependencies.

## Inputs

- Raw Workbench payload dictionaries.
- Optional turnover relation dictionaries.
- Explicit grouping service and serialization port.

## Outputs

- Grouped Workbench payload dictionaries.

## State And Events

The helper is pure and read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing grouped Workbench flow still calls `_group_row_payload(...)`, which now delegates to the helper.

## Tests And Guards

- Added `tests/test_workbench_group_row_payload_helper.py`.
- Updated static Guard coverage proving `Application` no longer owns raw-to-grouped extraction, ignored-row filtering or grouping invocation details.

## Out Of Scope

- cache/read payload helpers remain deferred.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
