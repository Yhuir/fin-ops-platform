---
status: complete
created_at: 2026-06-23
scope: reconciliation-workbench
---

# Summary

Completed.

## Result

- Added `workbench_invoice_direction` as the shared Workbench invoice direction contract.
- Normalized English `input/output`, Chinese `进项/销项`, and OA attachment invoice source rows before matching.
- Updated free matching, legacy matching rules, special matching detectors/service, candidate grouping, and amount check to reuse the shared contract.
- Bumped `workbench_matching_rules_version` / free engine `RULE_VERSION` to `2026-06-23-invoice-direction-normalization-v1`.
- Added production incident regression coverage for English `output` invoices no longer creating false expenditure three-way conflicts.

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_matching_rules tests.test_workbench_reconciliation_engine tests.test_workbench_amount_check_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping tests.test_workbench_matching_orchestrator -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_dirty_scope_worker tests.test_workbench_reconciliation_dirty_queue -v
```

The local incident-shaped reproduction now returns `oa_bank_invoice_exact_amount / paired` for `oa-pay-2065 + txn_imported_1415 + inv_imported_0086` and no `multiple_three_way_candidates` blocker.

## Production Follow-Up

Deploying this change should let the existing `workbench-matching` worker mark completed matching scopes with old `workbench_matching_rules_version` dirty and regenerate decisions/read models. Do not manually edit `read_model.workbench_reconciliation_decisions`.
