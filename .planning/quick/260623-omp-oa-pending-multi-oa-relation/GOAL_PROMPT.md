# Goal Prompt: OA Pending Multi-OA Relation Aggregation

Implement the plan in `PLAN.md` for OA 待付款核对 multi-OA relation aggregation.

## Objective

Make OA pending rows honor confirmed relation ownership:

- One confirmed active Workbench relation or active OA pending relation becomes one OA pending reconciliation row.
- If that relation contains multiple OA rows, OA side shows the summed OA amount and `+N`.
- If that relation contains multiple bank transactions, bank side shows the summed paid amount and `+N`.
- Members already represented inside the grouped row must not appear again as standalone rows.

## Required Workflow

1. Read `PLAN.md`.
2. Follow TDD:
   - Add failing regression tests first.
   - Verify they fail for the intended reason.
   - Implement minimal code.
   - Verify tests pass.
3. Keep changes scoped to OA pending relation aggregation/read model behavior and directly related tests/docs.
4. Do not alter Workbench relation creation, fuzzy matching, or production deployment.

## Key Acceptance Criteria

- A relation with 3 OA rows and 4 bank transactions appears as one OA pending row.
- OA payload has `amount` equal to OA total, `relationCount=3`, `detailMode=list`, and complete `summaries`.
- Bank payload has `paidTotal` equal to bank total, `relationCount=4`, `detailMode=list`, and complete `summaries`.
- Grouped OA/bank members are not emitted as separate rows.
- OA `+N` opens `relation-details?kind=oa`; bank `+N` opens `relation-details?kind=bank`.
- Payment status is derived from grouped OA total versus linked outflow bank total.

## Suggested Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_invoice_usage_collection_sql_runtime -v
cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx
```
