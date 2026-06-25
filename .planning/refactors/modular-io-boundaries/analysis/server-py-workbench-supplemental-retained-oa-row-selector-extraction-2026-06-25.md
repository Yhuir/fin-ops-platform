# server-py:workbench-supplemental-retained-oa-row-selector-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-supplemental-retained-oa-row-selection-audit`
**Next boundary:** `server-py:workbench-selected-scope-raw-oa-payload-audit`

## Purpose

Move supplemental retained OA row selection out of `Application._supplemental_retained_oa_row_ids(...)` into a focused selector service.

## Implementation

- Added `WorkbenchSupplementalRetainedOaRowSelector` in `backend/src/fin_ops_platform/services/workbench_supplemental_retained_oa_row_selector.py`.
- The selector owns:
  - manual retained OA row seed selection;
  - retained-OA supplemental relation iteration through an explicit relation read port;
  - OA/bank row id extraction from relation payloads;
  - live bank row resolution with missing-row skip behavior;
  - retention cutoff predicate application.
- `Application._supplemental_retained_oa_row_ids(...)` now delegates to the selector.
- `Application` remains the composition root and injects explicit callable dependencies.

## Inputs

- Retention cutoff date.
- Explicit callable ports for manual retained OA row ids, relation read port, live row resolution and cutoff predicate.

## Outputs

- Sorted retained OA row ids.

## State And Events

The selector is read-only. It does not know HTTP, repositories, auth, queues, caches, persistence or read-model freshness.

## Read Model/Freshness Contract

No read-model freshness semantics changed. The retained all-OA builder still calls `_supplemental_retained_oa_row_ids(...)`, which now delegates to the selector.

## Tests And Guards

- Added `tests/test_workbench_supplemental_retained_oa_row_selector.py`.
- Updated static Guard coverage proving the selector uses the retained-OA supplemental relation read port and that `Application` no longer owns the selection loop.

## Out Of Scope

- Selected-scope raw OA payload construction remains in `Application`.
- Retention date parsing remains in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
