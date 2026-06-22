# OA Pending Multi-OA Relation Aggregation Plan

## Goal

Fix OA 待付款核对 so one confirmed relation that contains multiple OA rows and multiple bank transactions renders as one reconciliation row, with `+N` detail affordances on both OA and bank sections and no duplicate standalone rows for grouped members.

## Context

- User screenshots show a relation with 3 OA rows, 4 bank transactions, and 1 input invoice.
- Current business expectation:
  - OA side should show the OA total and `+2`.
  - Bank side should show the bank paid total and `+3`.
  - Clicking OA `+N` opens OA details only.
  - Clicking bank `+N` opens bank details only.
  - Grouped OA/bank/invoice members must not appear as separate rows elsewhere in OA pending.
- Existing module docs already state that a Workbench active relation with multiple OA, bank, or invoice rows must become one OA pending row and use relation summaries/detail expansion.

## Current Findings

- Frontend already has support for OA relation detail buttons when `row.oa.detailMode === "list"` and `row.oa.relationCount > 1`.
- Query service already totals OA summaries in `_oa_group_payload`.
- Risk remains in rows/read-model construction: if the OA pending source for the current view only contains the primary OA record, relation rows can degrade to a single-OA payload while bank summaries still show multiple bank transactions.
- The fix must preserve relation ownership: all relation members included in the group must be removed from standalone row generation.

## Implementation Tasks

1. Add backend regression coverage first.
   - Cover a Workbench active relation containing three OA rows and four bank transactions.
   - Assert OA pending returns exactly one row for that relation.
   - Assert `row.oa.amount` is the OA total, `row.oa.relationCount == 3`, `row.oa.detailMode == "list"`, and all OA summaries are present.
   - Assert `row.bankTransaction.paidTotal` is the bank total, `relationCount == 4`, and all bank summaries are present.
   - Assert grouped OA members do not also appear as standalone rows.

2. Add read model builder/repository coverage if the failing path is SQL read model projection rather than live query service.
   - Assert `InvoiceUsageCollectionSqlProjectionBuilder.rebuild_oa_pending_payment_read_model_scope(...)` saves one grouped row with all OA and bank summaries.
   - Assert persisted read model payload round-trips relation counts and summaries.

3. Implement minimal backend fix.
   - Build OA relation summaries from the full confirmed relation membership, not only the primary/current OA row.
   - Preserve deterministic ordering.
   - Only synthesize or include OA summaries when the OA fact is available from an authoritative OA projection/source.
   - If relation membership references a missing OA fact, do not silently misrepresent totals; keep a diagnosable incomplete state rather than pretending it is a single-OA relation.
   - Ensure every grouped OA id is tracked so no grouped member is emitted as a standalone OA pending row.

4. Frontend validation.
   - Existing frontend behavior should be sufficient if payload is correct.
   - Add or adjust frontend regression only if current tests do not prove OA `+N` opens `kind=oa` and bank `+N` opens `kind=bank`.

5. Docs impact.
   - Update `docs/modules/oa-pending-payments/implementation-notes.md` and `tests.md` if behavior/test matrix changes.
   - Long-term product/API docs only need updates if response contract changes. Expected outcome is contract conformance, not a new contract.

## Acceptance Criteria

- A confirmed relation with 3 OA + 4 bank transactions + 1 invoice appears as one OA pending row.
- OA column shows total OA amount and `+2`.
- Bank column shows total paid amount and `+3`.
- Grouped OA and bank members are not emitted as separate rows in the same view/scope.
- OA `+N` detail request uses `relation-details?kind=oa`.
- Bank `+N` detail request uses `relation-details?kind=bank`.
- Payment status uses OA total versus linked outflow bank total.
- Search/filter can match child OA/bank text and still return the whole group row.
- Tests cover the applicable seven-category matrix:
  - Business core: amount/status/grouping rules.
  - Service/read model: projection and persistence if touched.
  - Frontend interaction: detail affordance routing if touched.
  - Existing regression: old single-OA and multi-bank rows remain valid.

## Verification Commands

Run the smallest relevant set first, then broaden if touched files require it:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_invoice_usage_collection_sql_runtime -v
cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx
```

## Out of Scope

- Changing Workbench relation creation semantics.
- Adding fuzzy matching.
- Changing OA MySQL writeback rules beyond using the correct grouped OA amount/status evidence.
- Production deploy, data repair, or manual read model rebuild.
