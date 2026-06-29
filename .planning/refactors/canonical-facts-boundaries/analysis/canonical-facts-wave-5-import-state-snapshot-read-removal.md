# Wave 5 - Import state snapshot read removal

日期：2026-06-28

## 目标

删除 PostgreSQL runtime 对旧 `app.app_settings state:imports` 和 `state:file_imports` JSON snapshot 的 fallback 读取。Import/file import facts 的读取必须来自 PostgreSQL canonical tables。

## 变更

- `PostgresStateStore._load_imports()` 不再 fallback 到 `_load_snapshot("imports")`。
- `PostgresStateStore._load_file_imports()` 不再 fallback 到 `_load_snapshot("file_imports")`。
- 新增测试证明即使旧 state key 存在，也不会作为 import/file import fact 返回。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_imports_do_not_fallback_to_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_file_imports_do_not_fallback_to_runtime_snapshot tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_snapshot_reads_are_confined_to_legacy_allowlist -v
```

结果：通过。

## 剩余

`state:imports` / `state:file_imports` 仅保留在测试 guard 和历史文档中，用于证明生产 bootstrap 不读旧 state keys。
