---
status: in_progress
created_at: 2026-06-23
scope: reconciliation-workbench
---

# GSD Quick Prompt: Workbench Invoice Direction Normalization

## Objective

Fix the production bug where Workbench automatic matching treats English `invoice_type=output` invoices as expenditure/input invoices, causing false `multiple_three_way_candidates` conflicts and preventing valid OA + bank + input invoice auto-pairing.

## Evidence

- Production `read_model.workbench_reconciliation_decisions` has open `free_matching_conflict` rows for `oa-pay-2065`, `txn_imported_1415`, and `inv_imported_0086`.
- The same three rows previously produced an expired paired decision with `rule_code=oa_bank_invoice_exact_amount`.
- Current code reproduces the failure: only the three selected rows pair; adding an English `output` invoice with nearby payment rows creates a false conflict.
- Root cause: multiple Workbench matching paths infer invoice direction by checking only whether `invoice_type` contains Chinese `销`, and otherwise default to outflow/expenditure.

## Scope

- Add a small shared Workbench invoice direction helper.
- Update free matching, legacy matching rules, special matching detectors/services, and candidate grouping paths that currently default invoice direction from the Chinese `销` substring.
- Bump Workbench matching rule version so completed production scopes are requeued by source-version freshness.
- Add regression tests for English `input/output` and the production incident shape.
- Update reconciliation-workbench module docs and this quick task summary.

## Out Of Scope

- No UI changes.
- No direct production data mutation.
- No manual edits to `read_model.workbench_reconciliation_decisions`.
- No changes to unrelated OA pending payment work currently dirty in the worktree.

## Acceptance Criteria

- English `input` invoices still match expenditure OA + outflow bank rows.
- English `output` invoices match income bank rows and use `buyer_name` as counterparty.
- English `output` invoices do not participate in expenditure OA-bank-input candidates.
- Unknown invoice types fail closed and do not silently default to expenditure/outflow.
- Existing Chinese `进项发票` and `销项发票` behaviors remain covered.
- Targeted Python tests pass.
- Documentation explains the production cause, the rule version bump, and the regeneration path.

## Verification Commands

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_matching_rules tests.test_workbench_reconciliation_engine -v
```

Optional broader checks if runtime allows:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator tests.test_workbench_candidate_grouping -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_dirty_scope_worker tests.test_workbench_reconciliation_dirty_queue -v
```
