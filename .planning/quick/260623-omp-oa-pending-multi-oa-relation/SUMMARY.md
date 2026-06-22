---
status: complete
completed_at: 2026-06-23
---

# Summary: OA Pending Multi-OA Relation Aggregation

## Outcome

Implemented the planned OA pending relation aggregation fix.

## Changes

- Added a regression test proving that a relation with 3 OA rows and 4 bank transactions returns one OA pending row with:
  - OA total `587000.00`
  - OA `relationCount=3`
  - bank paid total `587000.00`
  - bank `relationCount=4`
  - payment status `paid`
- Updated `OaPendingPaymentQueryService` so relation group construction preloads OA records from relation membership and uses projection lookup to complete OA summaries before calculating totals/status.
- Updated OA pending module implementation notes and test matrix.

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_invoice_usage_collection_sql_runtime -v
cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx
```

Both commands passed.

## Remaining Risk

Local synthetic tests do not prove the production screenshot sample until the production read model is rebuilt/refreshed and the real rows payload is inspected.
