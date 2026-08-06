# Deferred Items

## Resolved by 40-04

The three 40-03 verification discoveries were obsolete integration tests for contracts already
removed from production: `save_bank_flow_rule_batches`, the legacy batch-page `total` field,
and the retired `read_model.no_oa_bank_batch_rows` writer. Plan 40-04 removed those tests after
reproducing each failure against a disposable PostgreSQL database and confirming the canonical
no-OA route, command, and Workbench consumers remain covered.

No deferred items remain from 40-03.
