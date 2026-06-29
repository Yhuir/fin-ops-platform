# Wave 5 - Workbench candidate state snapshot write removal

日期：2026-06-28

## 目标

删除 `PostgresStateStore.save_workbench_candidate_matches(...)` 对旧 `app.app_settings state:workbench_candidate_matches` JSON snapshot 的写入。Workbench candidate matches 的持久化应走 `read_model.workbench_candidate_matches`，不能同时刷新旧 `state:*` fact。

## 变更

- `PostgresStateStore.save_workbench_candidate_matches(...)` 只委托 read model repository，不再调用 `_save_snapshot("workbench_candidate_matches", ...)`。
- 新增测试证明保存 candidate matches 后不会写 `state:workbench_candidate_matches`。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_candidate_matches_does_not_write_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_candidate_matches_ignore_runtime_snapshot_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_candidate_matches_restore_completed_scope_runs -v
```

结果：通过。

## 剩余

`repair_workbench_candidate_snapshot.py` 已在后续 wave 5 slice 删除；`state:workbench_candidate_matches` 不再保留该 repair 写入口。
