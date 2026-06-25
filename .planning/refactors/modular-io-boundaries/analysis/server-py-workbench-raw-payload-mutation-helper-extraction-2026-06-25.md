# server-py:workbench-raw-payload-mutation-helper-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-raw-payload-mutation-helper-audit`
**Next boundary:** `server-py:workbench-oa-raw-payload-signal-month-helper-audit`

## Purpose

Move raw Workbench payload replace/dedupe/summary mutation behavior out of `Application`.

## Implementation

- Added `WorkbenchRawPayloadMutationHelper` in `backend/src/fin_ops_platform/services/workbench_raw_payload_mutation_helper.py`.
- The helper owns:
  - replacing raw payload rows by id in paired/open sections;
  - deduping rows by id across paired/open sections;
  - recomputing raw payload summary counts and open danger exceptions.
- `Application._replace_raw_workbench_row(...)`, `_dedupe_raw_workbench_rows_by_id(...)` and `_refresh_raw_workbench_payload_summary(...)` now delegate to the helper to preserve existing callers.

## Inputs

- Raw Workbench payload dictionaries.
- Row type names.
- Replacement row dictionaries.
- Explicit serialization port for replacement values.

## Outputs

- In-place payload mutation and summary refresh.
- Replacement success boolean for row replacement.

## State And Events

The helper mutates only the payload object passed to it. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing canonical OA attachment repair flow still calls the same `Application` helper names, which now delegate to `WorkbenchRawPayloadMutationHelper`.

## Tests And Guards

- Added `tests/test_workbench_raw_payload_mutation_helper.py`.
- Updated static Guard coverage proving `Application` no longer owns replace/dedupe/summary mutation details.

## Out Of Scope

- OA raw payload signal/month helpers remain deferred to `server-py:workbench-oa-raw-payload-signal-month-helper-audit`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
