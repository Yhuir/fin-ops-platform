# GSD Closed-Loop Prompt: Pending Invoices Multi-Relation `+N`

## Objective

Execute the pending invoices multi-relation display plan end to end.

The pending invoices page must consume the unified `workbench_relation` fact source and display one grouped row per relation when a relation contains multiple OA rows, multiple bank transactions, or multiple invoices. Each section must show `+N` for the full count of that section's members, and clicking `+N` must open only that section's details.

## Required Behavior

- Use `workbench_relation` distribution/read model as the relation fact source.
- Add bank transaction grouping support to pending invoice rows.
- Suppress standalone duplicate rows for bank transactions already represented inside a grouped relation row.
- For count > 1, display only `+N` for that section; do not also display a member as a primary item.
- Keep single-item rows compatible with current UI behavior.
- Candidate relation evidence may be displayed, but linked-only status/payment decisions must remain linked-only.
- Preserve pending invoice read model freshness gates.

## Implementation Loop

1. Write backend failing tests for query service and SQL projection relation grouping.
2. Implement minimal backend helpers and row suppression.
3. Write frontend/API failing tests for `bank_transactions`, full-count `+N`, and kind-specific detail behavior.
4. Implement frontend mapper/table/drawer changes.
5. Update pending invoice docs and API contract docs.
6. Run focused verification and record results in `SUMMARY.md`.

## Acceptance Criteria

- Multi OA / multi bank / multi invoice relation renders as one pending invoice row.
- OA column shows `+N` for all OA members and opens only OA details.
- Bank transaction section shows `+N` for all bank members and opens only bank details.
- Invoice section shows `+N` for all invoice members and opens only invoice details.
- Members included in `+N` are not also shown as standalone primary items.
- Grouped bank members are not emitted as separate standalone pending invoice rows.
- Existing single item rows still render as before.

## Verification

Run at minimum:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_search_pending_sql_runtime tests.test_pending_invoice_api -v
cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx
```

Run docs verification if docs are changed:

```bash
bash scripts/verify.sh docs
```
