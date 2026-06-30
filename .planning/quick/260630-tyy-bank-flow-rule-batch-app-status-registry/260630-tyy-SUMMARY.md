---
status: complete
completed_at: 2026-06-30
---

# Quick Task 260630-tyy Summary

修复 `bank_flow_rule_batch` 已在 App Status read model registry 中登记、但缺少 migration storage contract 的不一致。

## Changes

- `READ_MODEL_STORAGE_CONTRACTS["bank_flow_rule_batch"]` 现在显式指向 `read_model.no_oa_bank_batch_rows`。
- 文档记录当前生产级合同：逻辑 read model 独立，物理表过渡期共享 no-OA rows，并通过 `relation_mode=bank_flow_rule_batch` 隔离。
- 未新增 `read_model.bank_flow_rule_batch_rows`；独立物理表拆分保留为单独迁移任务。

## Verification

- `PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_app_status_read_model_storage_contracts_are_declared -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_migrations.py -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_manifest.py -q`
- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_runtime_worker_registry.py -q`
- `bash scripts/verify.sh docs`
- `git diff --check -- tests/test_postgres_migrations.py docs/modules/bank-flow-rule-batches/implementation-notes.md docs/modules/read-models/implementation-notes.md .planning/quick/260630-tyy-bank-flow-rule-batch-app-status-registry/260630-tyy-PLAN.md`

## Result

The full `tests/test_postgres_migrations.py` file now passes.
