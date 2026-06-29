# Canonical Facts Wave 5: Matching State Write Removal

日期：2026-06-29

## Scope

删除 `PostgresStateStore.save({"matching": ...})` 对旧 `app.app_settings state:matching` JSON snapshot 的写入。

## Decision

- `PostgresStateStore._load_matching()` 已只读正式表 `app.matching_runs` / `app.matching_results`。
- 继续写 `state:matching` 只会留下旧 source-of-truth 残影，不会被 PostgreSQL runtime 读取。
- 本 slice 不新增 matching 写 port；普通 matching 持久化 owner 需要后续单独设计，不通过旧 `state:*` 恢复。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_matching_does_not_write_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_matching_does_not_fallback_to_runtime_snapshot -v
```

结果：通过。
