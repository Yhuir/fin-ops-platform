# server-py:workbench-oa-attachment-source-link-resolver-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-canonical-oa-attachment-raw-payload-repairer-extraction`
**Next boundary:** `server-py:workbench-oa-attachment-source-link-resolver-extraction`

## Purpose

Audit OA attachment source-link resolution helpers in `Application`.

## Findings

- `_oa_attachment_source_link_for_invoice(...)` owns source link normalization and `oa_form_id` fallback for attachment invoices.
- `_source_oa_id_for_attachment_link(...)` owns conversion from source link payload to matching input for `oa_attachment_matches_oa`.
- Both helpers are pure and already depend on shared `oa_attachment_best_source_link` / `oa_attachment_matches_oa` rules.
- Existing call sites can be preserved by keeping the `Application` static method names as compatibility delegates.

## Selected Boundary

Extract source-link normalization and source OA id resolution into `WorkbenchOaAttachmentSourceLinkResolver`.

## Deferrals

- Canonical OA attachment invoice row construction remains in `Application`.
- Raw payload replace/dedupe/summary helper extraction remains deferred.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
