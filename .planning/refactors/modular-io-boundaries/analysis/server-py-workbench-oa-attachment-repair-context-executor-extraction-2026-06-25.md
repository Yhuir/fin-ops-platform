# server-py:workbench-oa-attachment-repair-context-executor-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Completed

- Added `WorkbenchOaAttachmentRepairContextExecutor`.
- Moved active relation OA attachment context repair orchestration out of `Application._repair_active_relations_with_oa_attachment_context(...)`.
- Preserved `Application._repair_active_relations_with_oa_attachment_context(...)` as a compatibility delegate.
- Injected explicit ports for:
  - raw payload row indexing;
  - OA attachment context row grouping;
  - active relation reads;
  - dedicated-withdraw relation skip;
  - row type fallback;
  - value serialization;
  - amount-check calculation;
  - changed scope derivation;
  - command service creation;
  - pair relation persistence;
  - derived lifecycle emission.

## Local Proof

- Added `tests/test_workbench_oa_attachment_repair_context_executor.py`.
- Updated static Guards so `Application` delegates to the repair context executor while the executor preserves command-service `confirm_relation`, `replace_existing`, `before_relations`, history operation and lifecycle markers.
- Ran the existing Workbench v2 regression for repairing an active relation missing an OA attachment invoice.

## Remaining Work

The next local boundary is `server-py:workbench-oa-attachment-context-row-index-audit`, focused on `_raw_workbench_payload_rows_by_id(...)`, `_oa_attachment_context_row_ids_by_oa_id(...)`, `_invoice_row_is_oa_attachment_context(...)` and `_oa_id_from_attachment_invoice_id(...)`. Production browser/admin/write evidence remains deferred.
