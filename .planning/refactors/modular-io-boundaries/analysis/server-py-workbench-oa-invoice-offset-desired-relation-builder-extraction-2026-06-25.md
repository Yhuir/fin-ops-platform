# server-py:workbench-oa-invoice-offset-desired-relation-builder-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Completed

- Added `WorkbenchOaInvoiceOffsetDesiredRelationBuilder`.
- Moved desired relation construction out of `Application._oa_invoice_offset_desired_relations(...)`.
- Preserved `Application._oa_invoice_offset_desired_relations(...)` as a compatibility delegate.
- Injected explicit ports for:
  - applicant names;
  - value serialization;
  - attachment invoice row matching;
  - manual-conflict detection;
  - month scope derivation.

## Local Proof

- Added `tests/test_workbench_oa_invoice_offset_desired_relation_builder.py`.
- Added static Guard `test_workbench_oa_invoice_offset_desired_relation_builder_extraction_stays_local`.
- The Guard prevents desired relation construction details, `CASE-OA-OFFSET` ids, row type shaping, month scope assignment, HTTP dependencies, cache writes and relation sync side effects from leaking into the wrong layer.

## Remaining Work

relation sync side effects remain deferred. The next local boundary is `server-py:workbench-oa-invoice-offset-sync-executor-audit`, focused on whether confirm/cancel/persist/lifecycle orchestration can be safely extracted behind explicit ports.
