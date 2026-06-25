# server-py:workbench-raw-payload-assembler-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-raw-payload-builder-audit`
**Next boundary:** `server-py:workbench-live-oa-raw-payload-source-audit`

## Purpose

Move legacy raw Workbench payload construction orchestration out of `Application._build_raw_workbench_payload(...)` while preserving existing live/OA source, relation repair, pair relation and override behavior.

## Implementation

- Added `WorkbenchRawPayloadAssembler` in `backend/src/fin_ops_platform/services/workbench_raw_payload_assembler.py`.
- The assembler owns the ordered raw payload orchestration:
  - live-vs-OA source choice;
  - live auto-pair sync before live payload build;
  - OA invoice offset auto-pair sync;
  - OA attachment relation repair;
  - pair relation application with `supplement_missing_pair_relation_rows` passthrough;
  - override application.
- `Application._build_raw_workbench_payload(...)` now delegates to `self._workbench_raw_payload_assembler().build(...)`.
- `Application` remains the composition root and injects explicit callable dependencies.

## Inputs

- Month and `supplement_missing_pair_relation_rows`.
- Explicit callable ports for source detection, live/OA payload build, relation sync/repair, pair relation application and override application.

## Outputs

- Legacy raw Workbench payload after pair relation and override application.

## State And Events

The assembler itself does not know HTTP, repositories, auth, queues, caches, persistence or read-model freshness. Existing side effects remain in the injected helper ports and are unchanged.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing local callers still call `_build_raw_workbench_payload(...)`, which now delegates to the assembler.

## Tests And Guards

- Added `tests/test_workbench_raw_payload_assembler.py`.
- Preserved existing SQL/read-model tests that assert API paths do not synchronously rebuild raw payloads.
- Added static Guard coverage proving `_build_raw_workbench_payload(...)` no longer owns raw orchestration steps and the assembler has no HTTP/write/runtime side-effect dependencies.

## Out Of Scope

- Live/OA raw payload source helper bodies remain in `Application`.
- OA retention internals remain in `Application`.
- Pair relation application internals remain in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
