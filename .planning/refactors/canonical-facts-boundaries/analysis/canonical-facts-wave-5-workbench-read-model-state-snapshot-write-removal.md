# Wave 5 - Workbench read model state snapshot write removal

日期：2026-06-28

## 目标

删除 `PostgresStateStore.save_workbench_read_models(...)` 对旧 `app.app_settings state:workbench_read_models` JSON snapshot 的写入。Workbench read model 的持久化应走 `read_model.workbench_*` 表，不能同时刷新旧 `state:*` fact。

## 变更

- `PostgresStateStore.save_workbench_read_models(...)` 只委托 read model repository，不再调用 `_save_snapshot("workbench_read_models", ...)`。
- 新增测试证明保存 Workbench read model 后不会写 `state:workbench_read_models`。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_workbench_read_models_does_not_write_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_workbench_read_models_ignore_runtime_snapshot_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_workbench_read_models_do_not_fallback_to_runtime_snapshot_when_sql_empty -v
```

结果：通过。

## 剩余

`state:workbench_read_models` 仅保留在测试 fallback fixtures 和历史文档中，用于证明 PostgreSQL read model 不读旧 fallback。
