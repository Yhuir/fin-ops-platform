# server-py:workbench-live-oa-raw-payload-source-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-raw-payload-assembler-extraction`
**Selected next boundary:** `server-py:workbench-live-payload-builder-extraction`

## Purpose

Audit `_build_live_workbench_row_payload(...)`, `_build_oa_workbench_row_payload(...)`, retained all-OA payload source behavior and canonical OA attachment promotion helpers.

## Findings

- `_build_live_workbench_row_payload(...)` is a small source composition step: get live rows, get OA rows, merge them, serialize the merged payload.
- `_build_oa_workbench_row_payload(...)` is broader and still must remain compatible with existing tests that patch the app method directly.
- `_build_retained_all_oa_row_payload(...)` and canonical OA attachment promotion helpers have wider OA adapter, retention, import and promotion side effects.

## Decision

Select `server-py:workbench-live-payload-builder-extraction` as the next narrow local implementation boundary.

This moves only the live payload merge orchestration into a builder while keeping `_build_oa_workbench_row_payload(...)` and retained all-OA behavior intact as compatibility boundaries.

## Out Of Scope

- No production browser/admin/write validation.
- No `_build_oa_workbench_row_payload(...)` migration.
- No retained all-OA source behavior migration.
- No canonical OA attachment promotion migration.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.
