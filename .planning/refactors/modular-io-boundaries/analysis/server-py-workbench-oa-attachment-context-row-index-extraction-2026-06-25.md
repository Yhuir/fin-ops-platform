# server-py:workbench-oa-attachment-context-row-index-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Completed

- Added `WorkbenchOaAttachmentContextRowIndex`.
- Moved raw payload row indexing, OA attachment invoice context detection, derived/source-link OA matching and attachment invoice id fallback matching out of `Application`.
- Preserved existing `Application` helper names as compatibility delegates.
- Injected explicit matching dependencies:
  - `attachment_parent_oa_id`;
  - `attachment_matches_oa`;
  - `attachment_row_id_matches_oa`.

## Local Proof

- Added `tests/test_workbench_oa_attachment_context_row_index.py`.
- Added static Guard `test_workbench_oa_attachment_context_row_index_extraction_stays_local`.
- Guard prevents row-index/source matching details and forbidden HTTP/read-model/cache dependencies from leaking into the wrong layer.

## Remaining Work

The next local boundary is `server-py:workbench-raw-payload-row-id-set-helper-audit`, focused on `_raw_workbench_payload_row_ids(...)`. Production browser/admin/write evidence remains deferred.
