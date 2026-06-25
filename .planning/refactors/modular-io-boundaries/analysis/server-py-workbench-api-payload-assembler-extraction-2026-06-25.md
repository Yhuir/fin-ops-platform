# server-py:workbench-api-payload-assembler-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-legacy-api-payload-builder-audit`
**Next boundary:** `server-py:workbench-raw-payload-builder-audit`

## Purpose

Move legacy grouped Workbench API payload post-processing orchestration out of `Application._build_api_workbench_payload(...)` while preserving the existing raw payload builder and business helper behavior.

## Implementation

- Added `WorkbenchApiPayloadAssembler` in `backend/src/fin_ops_platform/services/workbench_api_payload_assembler.py`.
- The assembler owns the ordered grouped payload pipeline:
  - read model provider call with `ensure_candidate_matches=True`;
  - OA retention application;
  - ETC invoice summary row append;
  - invoice inventory injection;
  - final tag derivation.
- `Application._build_api_workbench_payload(...)` now delegates to `self._workbench_api_payload_assembler().build(...)`.
- `Application` remains the composition root and injects explicit callable dependencies.

## Inputs

- Month and visibility key.
- Explicit callable ports for read model creation, retention, ETC summary append, invoice inventory and tag derivation.

## Outputs

- Legacy grouped Workbench API payload.

## State And Events

The assembler itself does not know HTTP, repositories, auth, queues, caches, persistence or read-model freshness. Any side effects remain in the injected existing helpers and are unchanged.

## Read Model/Freshness Contract

No read-model freshness semantics changed. The assembler preserves the existing `ensure_candidate_matches=True` call and returns the same grouped payload after the same post-processing steps.

## Tests And Guards

- Added `tests/test_workbench_api_payload_assembler.py`.
- Preserved existing legacy `/api/workbench` SQL and grouped payload tests.
- Added static Guard coverage proving `_build_api_workbench_payload(...)` no longer owns the assembler steps and the assembler has no HTTP/write/runtime side-effect dependencies.

## Out Of Scope

- `_build_raw_workbench_payload` remains in `Application`.
- OA retention internals remain in `Application`.
- Tag derivation internals remain in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
