# server-py:workbench-raw-payload-row-id-set-helper-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Completed

- Added `WorkbenchOaAttachmentContextRowIndex.raw_payload_row_ids(...)`.
- Moved generic raw payload row-id set extraction out of `Application._raw_workbench_payload_row_ids(...)`.
- Preserved `Application._raw_workbench_payload_row_ids(...)` as a compatibility delegate.
- Reused the existing row-index owner instead of creating a one-method class.

## Local Proof

- Extended `tests/test_workbench_oa_attachment_context_row_index.py`.
- Extended static Guard `test_workbench_oa_attachment_context_row_index_extraction_stays_local`.

## Remaining Work

The next local boundary is `server-py:workbench-pair-relation-display-payload-audit`, focused on relation display and pair metadata helpers still owned by `Application`. Production browser/admin/write evidence remains deferred.
