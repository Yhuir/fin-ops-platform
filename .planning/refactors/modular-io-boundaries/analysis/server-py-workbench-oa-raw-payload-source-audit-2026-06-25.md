# server-py:workbench-oa-raw-payload-source-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-live-payload-builder-extraction`
**Selected next boundary:** `server-py:workbench-oa-payload-builder-extraction`

## Purpose

Audit `_build_oa_workbench_row_payload(...)`, `_build_retained_all_oa_row_payload(...)`, retained month/supplemental row selection and canonical OA attachment promotion.

## Findings

- `_build_oa_workbench_row_payload(...)` owns a small orchestration boundary:
  - choose retained all-OA path for all-scope Mongo adapter;
  - otherwise load OA workbench payload and serialize it;
  - promote OA attachment invoices for month scopes;
  - append canonical OA attachment invoice rows.
- `_build_retained_all_oa_row_payload(...)` is broader and owns retention cutoff, retained month discovery, supplemental row sync, parse suppression and selected-scope payload construction.
- Canonical OA attachment promotion is a separate side-effecting helper already guarded by recognition-service tests.

## Decision

Select `server-py:workbench-oa-payload-builder-extraction` as the next narrow local implementation boundary.

This moves only OA source orchestration out of `Application._build_oa_workbench_row_payload(...)` and keeps retained all-OA behavior plus canonical promotion internals deferred.

## Out Of Scope

- No production browser/admin/write validation.
- No `_build_retained_all_oa_row_payload(...)` migration.
- No retained month/supplemental row selection migration.
- No canonical OA attachment promotion migration.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.
