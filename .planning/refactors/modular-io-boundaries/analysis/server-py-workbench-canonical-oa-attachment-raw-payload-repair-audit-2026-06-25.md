# server-py:workbench-canonical-oa-attachment-raw-payload-repair-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-oa-retention-date-parser-extraction`
**Next boundary:** `server-py:workbench-canonical-oa-attachment-raw-payload-repairer-extraction`

## Purpose

Audit canonical OA attachment invoice raw payload repair logic in `Application`.

## Findings

- `_append_canonical_oa_attachment_invoice_rows(...)` owns payload repair orchestration:
  - scanning raw payload OA rows and existing invoice ids;
  - iterating imported invoices;
  - resolving source links and source OA ids;
  - building canonical invoice rows;
  - replacing existing invoice rows or appending new rows;
  - deduping and refreshing raw payload summary.
- The orchestration can be extracted with explicit ports while preserving source-link parsing and canonical row construction as separate deferred boundaries.
- The extracted orchestration is payload-local and does not need HTTP, auth, queues, caches, read-model readiness or persistence.

## Selected Boundary

Extract payload repair orchestration into `WorkbenchCanonicalOaAttachmentRawPayloadRepairer`.

## Deferrals

- `_oa_attachment_source_link_for_invoice(...)` remains in `Application`.
- `_source_oa_id_for_attachment_link(...)` remains in `Application`.
- `_canonical_oa_attachment_invoice_workbench_row(...)` remains in `Application`.
- `_replace_raw_workbench_row(...)`, `_dedupe_raw_workbench_rows_by_id(...)` and `_refresh_raw_workbench_payload_summary(...)` remain as explicit compatibility ports.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
