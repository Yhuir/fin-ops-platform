# server-py:workbench-cache-read-payload-helper-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-group-row-payload-helper-extraction`
**Next boundary:** `server-py:workbench-cache-read-payload-helper-extraction`

## Purpose

Audit Workbench cached/read payload readiness helpers in `Application`.

## Findings

- `_can_use_cached_workbench_payload(...)` owns cached payload readiness, schema/hash/parser checks and summary gate behavior.
- `_can_persist_workbench_payload(...)` and `_can_fallback_to_stale_workbench_payload(...)` own persistence/fallback gates based on OA status readiness.
- `_oa_status_is_ready_for_cache(...)` owns Mongo vs non-Mongo OA status semantics.
- `_cached_payload_needs_oa_invoice_offset_rebuild(...)` is a related but separate OA invoice offset rebuild detector and can be kept as an explicit port for this slice.

## Selected Boundary

Extract cached/read payload readiness decisions into `WorkbenchCacheReadPayloadHelper`.

## Deferrals

- OA invoice offset rebuild helper extraction remains deferred.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
