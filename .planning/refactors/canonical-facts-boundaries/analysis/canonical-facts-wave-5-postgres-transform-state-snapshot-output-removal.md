# Wave 5 - Postgres Transform state:* Snapshot Output Removal

日期：2026-06-29

## Target

删除 staging -> PostgreSQL 转换工具中继续生成旧 `app.app_settings state:*` snapshot rows 的分支。

## Changes

- `no_oa_bank_batches_meta` 不再输出 `state:no_oa_bank_batches`。
- `bank_transaction_categories_meta` 不再输出 `state:bank_transaction_categories`，但仍保留 category audit events。
- `turnover_relations_meta` 不再输出 `state:turnover_relations`。
- 删除 `settings_snapshot_row(...)` helper。
- `tests/test_postgres_transform.py` 改为负向断言旧 `state:*` rows 不会被生成。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/postgres_transform.py tests/test_postgres_transform.py
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_transform.py -q
```

## Result

PostgreSQL migration transform no longer repopulates old runtime settings snapshot facts for no-OA batches, bank transaction categories or turnover relations.
