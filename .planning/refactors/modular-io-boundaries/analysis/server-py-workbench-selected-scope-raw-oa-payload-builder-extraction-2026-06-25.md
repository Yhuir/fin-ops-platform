# server-py:workbench-selected-scope-raw-oa-payload-builder-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-selected-scope-raw-oa-payload-audit`
**Next boundary:** `server-py:workbench-retention-date-parser-audit`

## Purpose

Move selected-scope raw OA payload construction out of `Application._raw_oa_payload_for_selected_scope(...)` into a focused builder service.

## Implementation

- Added `WorkbenchSelectedScopeRawOaPayloadBuilder` in `backend/src/fin_ops_platform/services/workbench_selected_scope_raw_oa_payload_builder.py`.
- The builder owns:
  - retained OA row id merging from supplemental and manual sources;
  - record snapshot filtering for selected months and retained OA ids;
  - OA attachment invoice inclusion via `derived_from_oa_id`;
  - paired/open section assignment;
  - row serialization;
  - summary construction.
- `Application._raw_oa_payload_for_selected_scope(...)` now delegates to the builder.
- `Application` remains the composition root and injects explicit callable dependencies.

## Inputs

- Selected month scopes.
- Supplemental retained OA row ids.
- Explicit callable ports for manual retained OA row ids, record snapshots, row serialization and OA status payload.

## Outputs

- A raw OA payload with `month`, `oa_status`, `summary`, `paired` and `open`.

## State And Events

The builder is read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. The retained all-OA builder still calls `_raw_oa_payload_for_selected_scope(...)`, which now delegates to the selected-scope builder.

## Tests And Guards

- Added `tests/test_workbench_selected_scope_raw_oa_payload_builder.py`.
- Updated static Guard coverage proving `Application` no longer owns record snapshot filtering, section assignment or summary construction for selected-scope raw OA payloads.

## Out Of Scope

- Retention date parsing remains in `Application`.
- Canonical OA attachment invoice append/replace/dedupe/summary repair remains in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
