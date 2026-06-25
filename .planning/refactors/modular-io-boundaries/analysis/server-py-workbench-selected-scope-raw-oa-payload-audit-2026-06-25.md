# server-py:workbench-selected-scope-raw-oa-payload-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-supplemental-retained-oa-row-selector-extraction`
**Next boundary:** `server-py:workbench-selected-scope-raw-oa-payload-builder-extraction`

## Purpose

Audit `Application._raw_oa_payload_for_selected_scope(...)` and identify the next narrow local implementation boundary.

## Findings

- The method builds selected-scope raw OA payloads for retained all-OA scope.
- It owns record snapshot filtering, retained OA id merging, OA attachment invoice inclusion, row serialization, paired/open section assignment and summary construction.
- It is read-only and does not need HTTP, auth, repositories, queues, caches, read-model readiness or persistence.
- Its required I/O can be expressed as explicit ports:
  - manual retained OA row ids;
  - record snapshots;
  - row serialization;
  - OA status payload.

## Selected Boundary

Extract selected-scope raw OA payload construction into `WorkbenchSelectedScopeRawOaPayloadBuilder`.

## Deferrals

- Retention date parsing remains in `Application`.
- Canonical OA attachment invoice append/replace/dedupe/summary repair remains in `Application`.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
