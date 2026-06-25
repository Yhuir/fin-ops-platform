# server-py:workbench-live-oa-merge-helper-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-oa-raw-payload-signal-month-helper-extraction`
**Next boundary:** `server-py:workbench-live-oa-merge-helper-extraction`

## Purpose

Audit live/OA raw payload merge helpers that remain in `Application`.

## Findings

- `_merge_live_workbench_with_oa_rows(...)` owns merging live payloads with OA raw rows and bringing across only OA attachment invoice rows.
- `_dedupe_workbench_rows_by_id_preferring_last(...)` owns row-id dedupe with later rows winning.
- `_merge_live_workbench_with_oa(...)` still performs grouped merge compatibility by calling `_group_row_payload(...)` after row merge.
- The row merge and dedupe behavior is pure except for serialization, which can be injected as a port.

## Selected Boundary

Extract live/OA row merge and row-id dedupe into `WorkbenchLiveOaMergeHelper`.

## Deferrals

- `_group_row_payload(...)` and grouped merge boundaries remain in `Application` for the next slice.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
