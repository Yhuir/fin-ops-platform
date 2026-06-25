# server-py:workbench-oa-invoice-offset-sync-executor-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Completed

- Added `WorkbenchOaInvoiceOffsetSyncExecutor`.
- Moved OA invoice offset auto-pair sync orchestration out of `Application._sync_oa_invoice_offset_auto_pair_relations(...)`.
- Preserved `Application._sync_oa_invoice_offset_auto_pair_relations(...)` as a compatibility delegate.
- Injected explicit ports for:
  - desired relation construction;
  - raw payload row id extraction;
  - active relation reads by mode;
  - command service creation;
  - pair relation persistence;
  - derived lifecycle emission.

## Local Proof

- Added `tests/test_workbench_oa_invoice_offset_sync_executor.py`.
- Updated static Guards so `Application` delegates to the sync executor while the executor retains command-service confirm/cancel and relation-mode constrained active reads.
- The unit tests cover unchanged active relations, confirm, cancel, and out-of-current-payload no-cancel behavior.

## Remaining Work

The next local boundary is `server-py:workbench-oa-attachment-repair-context-audit`, focused on `_repair_active_relations_with_oa_attachment_context(...)`. Production browser/admin/write evidence remains deferred.
