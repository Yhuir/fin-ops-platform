# server-py:workbench-retained-all-oa-payload-builder-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-retained-all-oa-payload-audit`
**Next boundary:** `server-py:workbench-supplemental-retained-oa-row-selection-audit`

## Purpose

Move retained all-OA raw payload orchestration out of `Application._build_retained_all_oa_row_payload(...)` while preserving retained month selection, supplemental retained OA row selection and selected-scope raw OA payload internals.

## Implementation

- Added `WorkbenchRetainedAllOaPayloadBuilder` in `backend/src/fin_ops_platform/services/workbench_retained_all_oa_payload_builder.py`.
- The builder owns:
  - no-cutoff all-scope payload load and promotion;
  - retained month and supplemental row orchestration;
  - background parse suppression around retained/supplemental sync;
  - selected-scope payload call and promotion scope calculation.
- `Application._build_retained_all_oa_row_payload(...)` now delegates to `self._workbench_retained_all_oa_payload_builder().build()`.
- `Application` remains the composition root and injects explicit callable dependencies.

## Inputs

- Explicit callable ports for retention cutoff, all-scope payload load, serialization, signal detection, promotion, retained months, supplemental retained OA rows, parse suppression, sync, snapshots, selected-scope raw OA payload and month-scope validation.

## Outputs

- Retained all-scope OA raw payload.

## State And Events

The builder itself does not know HTTP, repositories, auth, queues, caches, persistence or read-model freshness. Existing side effects remain in the injected helper ports and are unchanged.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Supplemental retained OA row selection and selected-scope raw OA payload construction remain compatibility boundaries for later slices.

## Tests And Guards

- Added `tests/test_workbench_retained_all_oa_payload_builder.py`.
- Added static Guard coverage proving `_build_retained_all_oa_row_payload(...)` no longer owns retained-all orchestration and the builder has no HTTP/write/runtime side-effect dependencies.

## Out Of Scope

- Supplemental retained OA row selection remains in `Application`.
- Selected-scope raw OA payload construction remains in `Application`.
- Canonical OA attachment promotion internals remain in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
