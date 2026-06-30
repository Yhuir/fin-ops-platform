---
status: in_progress
mode: quick-validate
must_haves:
  truths:
    - bank_flow_rule_batch remains a registered App Status read model.
    - Current physical storage is shared with no_oa_bank_batch and isolated by relation_mode=bank_flow_rule_batch.
    - No new physical table is introduced in this fix.
  artifacts:
    - tests/test_postgres_migrations.py
    - docs/modules/bank-flow-rule-batches/implementation-notes.md
    - docs/modules/read-models/implementation-notes.md
  key_links:
    - docs/modules/bank-flow-rule-batches/boundary-io.md
    - docs/architecture/module-boundaries/read-model-contracts.md
---

# Quick Task 260630-tyy: bank_flow_rule_batch App Status storage contract

## Design

Production-grade fix is to keep `bank_flow_rule_batch` registered and declare its current storage contract explicitly:
`bank_flow_rule_batch -> read_model.no_oa_bank_batch_rows`.

Reason: the module already has an independent route, service, read model key, worker event, App Status registry entry and manifest entry. The only missing piece is the migration test's storage-contract map. Current docs say physical storage split is a later migration and shared storage is isolated by `relation_mode=bank_flow_rule_batch`.

## Tasks

1. Patch `READ_MODEL_STORAGE_CONTRACTS`.
   - files: `tests/test_postgres_migrations.py`
   - action: add `bank_flow_rule_batch` mapping to `read_model.no_oa_bank_batch_rows`
   - verify: full `tests/test_postgres_migrations.py`
   - done: mapping set equals App Status registry

2. Record the production storage contract.
   - files: `docs/modules/bank-flow-rule-batches/implementation-notes.md`, `docs/modules/read-models/implementation-notes.md`
   - action: document this as shared physical storage contract, not table creation
   - verify: `bash scripts/verify.sh docs`
   - done: future developers see why no new table was added

3. Verify focused read model contracts.
   - files: tests only
   - action: run postgres migration and read model manifest tests relevant to registry/storage/worker
   - verify: `pytest` targeted commands
   - done: local failure removed without expanding scope
