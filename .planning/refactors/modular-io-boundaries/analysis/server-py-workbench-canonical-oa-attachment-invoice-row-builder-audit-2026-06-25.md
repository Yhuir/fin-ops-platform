# server-py:workbench-canonical-oa-attachment-invoice-row-builder-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-oa-attachment-source-link-resolver-extraction`
**Next boundary:** `server-py:workbench-canonical-oa-attachment-invoice-row-builder-extraction`

## Purpose

Audit canonical OA attachment invoice row construction in `Application`.

## Findings

- `_canonical_oa_attachment_invoice_workbench_row(...)` owns invoice field mapping, tags, detail fields, summary fields, relation payload construction and source metadata.
- The method is pure relative to app state except for helper calls:
  - `_workbench_invoice_money_text(...)`;
  - `_first_month_from_oa_row(...)`;
  - `InvoiceType.OUTPUT.value`.
- `_append_unique_text(...)` and `_oa_display_number_for_attachment_invoice(...)` are only used by this construction path and can move with the builder.

## Selected Boundary

Extract canonical OA attachment invoice row construction into `WorkbenchCanonicalOaAttachmentInvoiceRowBuilder`.

## Deferrals

- Raw payload replace/dedupe/summary helper extraction remains deferred.
- OA month extraction remains in `Application` because it is also used by raw payload month collection.
- Production browser/admin/write evidence remains deferred.

## Completion Semantics

This audit may be marked `analysis-closed` after the implementation boundary is selected and recorded. It does not claim Workbench module/global closure.
