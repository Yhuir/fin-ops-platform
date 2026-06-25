# server-py:workbench-group-row-payload-helper-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-live-oa-merge-helper-extraction`
**Next boundary:** `server-py:workbench-group-row-payload-helper-extraction`

## Purpose

Audit `_group_row_payload(...)` and grouped merge compatibility.

## Findings

- `_group_row_payload(...)` owns raw payload section extraction, ignored-row filtering, grouping service invocation and OA status carry-over.
- The behavior can be expressed through explicit ports:
  - grouping service;
  - serialization function.
- `_merge_live_workbench_with_oa(...)` remains a compatibility wrapper that merges raw rows first and then delegates to `_group_row_payload(...)`.

## Selected Boundary

Extract raw-to-grouped payload behavior into `WorkbenchGroupRowPayloadHelper`.

## Deferrals

- Cache/read payload helpers remain in `Application`.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
