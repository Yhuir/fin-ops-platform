# server-py:workbench-oa-invoice-offset-rebuild-helper-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Completed

- Added `WorkbenchOaInvoiceOffsetRebuildHelper`.
- Moved cached payload rebuild detection out of `Application._cached_payload_needs_oa_invoice_offset_rebuild(...)`.
- Moved OA attachment invoice rows filtering out of `Application._oa_attachment_invoice_rows_for_oa(...)`.
- Preserved explicit dependency injection for:
  - `applicant_names_provider`;
  - `attachment_matches_oa`;
  - `offset_tag`.
- Kept `Application` compatibility helper names as thin delegates.

## Local Proof

- Added `tests/test_workbench_oa_invoice_offset_rebuild_helper.py`.
- Added static Guard `test_workbench_oa_invoice_offset_rebuild_helper_extraction_stays_local`.
- The Guard prevents applicant settings, attachment invoice source checks, offset tag/cost exclusion checks, HTTP dependencies, cache writes, read-model gateway usage and server imports from leaking into the helper or back into `Application` helper bodies.

## Remaining Work

The next local boundary is `server-py:workbench-oa-invoice-offset-relation-sync-audit`, focused on desired relation construction and sync orchestration. Production browser/admin/write evidence remains deferred.
