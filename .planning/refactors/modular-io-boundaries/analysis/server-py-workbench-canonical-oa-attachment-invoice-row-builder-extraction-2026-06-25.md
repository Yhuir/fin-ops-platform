# server-py:workbench-canonical-oa-attachment-invoice-row-builder-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-canonical-oa-attachment-invoice-row-builder-audit`
**Next boundary:** `server-py:workbench-raw-payload-mutation-helper-audit`

## Purpose

Move canonical OA attachment invoice row construction out of `Application`.

## Implementation

- Added `WorkbenchCanonicalOaAttachmentInvoiceRowBuilder` in `backend/src/fin_ops_platform/services/workbench_canonical_oa_attachment_invoice_row_builder.py`.
- The builder owns:
  - invoice field mapping;
  - tags and source links normalization;
  - detail and summary fields;
  - pending collection relation payload construction;
  - source metadata fields;
  - OA display number fallback.
- `Application._canonical_oa_attachment_invoice_workbench_row(...)` now delegates to the builder.
- Removed `Application._append_unique_text(...)` and `_oa_display_number_for_attachment_invoice(...)` after moving their only usage into the builder.

## Inputs

- Invoice-like objects.
- Normalized source-link dictionaries.
- Source OA rows.
- Explicit ports for money formatting, OA month extraction and output invoice type value.

## Outputs

- Canonical Workbench invoice row dictionaries for OA attachment invoices.

## State And Events

The builder is pure and read-only. It does not know HTTP, repositories, auth, queues, caches, persistence, read-model freshness or worker state.

## Read Model/Freshness Contract

No read-model freshness semantics changed. Existing raw payload repair flow still calls `_canonical_oa_attachment_invoice_workbench_row(...)`, which now delegates to the builder.

## Tests And Guards

- Added `tests/test_workbench_canonical_oa_attachment_invoice_row_builder.py`.
- Updated static Guard coverage proving `Application` no longer owns canonical OA attachment invoice field mapping.

## Out Of Scope

- Raw payload replace/dedupe/summary helper extraction remains deferred.
- OA month extraction remains in `Application`.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
