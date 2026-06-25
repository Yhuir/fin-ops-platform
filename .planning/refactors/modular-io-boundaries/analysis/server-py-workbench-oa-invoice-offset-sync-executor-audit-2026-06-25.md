# server-py:workbench-oa-invoice-offset-sync-executor-audit

Date: 2026-06-25
Status: analysis-closed

## Scope

Audited the remaining `_sync_oa_invoice_offset_auto_pair_relations(...)` side effects after desired relation builder extraction.

## Findings

- The remaining function is orchestration rather than HTTP handling:
  - desired relation lookup;
  - raw payload scanned row id extraction;
  - active auto-relation read through `WorkbenchOaInvoiceOffsetRelationReadPort`;
  - desired-vs-active comparison;
  - confirm/cancel command calls;
  - changed case id and scope collection;
  - pair relation persistence;
  - derived lifecycle emission.
- The orchestration can be moved behind explicit ports without giving the service direct access to `Application`, HTTP state, repositories or read-model gateways.
- Required local proof must cover unchanged, confirm, cancel, and out-of-current-payload no-cancel behavior.

## Decision

Select `server-py:workbench-oa-invoice-offset-sync-executor-extraction`.

## Deferred

- Full production browser/admin/write evidence remains deferred.
- Broader Workbench relation repair extraction remains out of this slice.
