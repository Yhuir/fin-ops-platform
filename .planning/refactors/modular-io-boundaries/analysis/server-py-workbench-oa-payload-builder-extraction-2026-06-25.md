# server-py:workbench-oa-payload-builder-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-oa-raw-payload-source-audit`
**Next boundary:** `server-py:workbench-retained-all-oa-payload-audit`

## Purpose

Move OA-source Workbench raw payload orchestration out of `Application._build_oa_workbench_row_payload(...)` while preserving retained all-OA behavior and canonical OA attachment promotion internals.

## Implementation

- Added `WorkbenchOaPayloadBuilder` in `backend/src/fin_ops_platform/services/workbench_oa_payload_builder.py`.
- The builder owns:
  - retained all-OA path selection through an explicit predicate;
  - normal OA payload load and serialization;
  - month-scope OA attachment promotion trigger;
  - canonical OA attachment invoice row append.
- `Application._build_oa_workbench_row_payload(...)` now delegates to `self._workbench_oa_payload_builder().build(month)`.
- `Application` remains the composition root and injects explicit callable dependencies.

## Inputs

- Month.
- Explicit callable ports for retained-all predicate, retained-all payload build, normal OA payload load, serialization, month-scope check, promotion and canonical append.

## Outputs

- OA-source Workbench raw payload.

## State And Events

The builder itself does not know HTTP, repositories, auth, queues, caches, persistence or read-model freshness. Existing side effects remain in the injected helper ports and are unchanged.

## Read Model/Freshness Contract

No read-model freshness semantics changed. `_build_retained_all_oa_row_payload` remains the compatibility boundary for retained all-OA behavior.

## Tests And Guards

- Added `tests/test_workbench_oa_payload_builder.py`.
- Added static Guard coverage proving `_build_oa_workbench_row_payload(...)` no longer owns OA source orchestration and the builder has no HTTP/write/runtime side-effect dependencies.

## Out Of Scope

- `_build_retained_all_oa_row_payload(...)` remains in `Application`.
- Retained month and supplemental row selection remain in `Application`.
- Canonical OA attachment promotion internals remain in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
