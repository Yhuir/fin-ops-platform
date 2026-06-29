# Wave 5 - ApplicationStateStore workbench overrides Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 workbench overrides / exception cases 的旧 App Mongo 分支。

## 变更

- `save_workbench_overrides(...)` 只保留本地 pickle I/O。
- `save_workbench_exception_cases(...)` 只保留本地 pickle I/O。
- 旧 Mongo-specific tests 收敛为本地 store snapshot 测试。
- 新增 static guard 禁止这组方法重新接入 App Mongo。

## 边界结论

- 生产 workbench overrides / exception cases facts 仍由 PostgreSQL workbench repository 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_workbench_overrides_persists_local_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_overrides_accepts_changed_rows_for_local_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_exception_cases_persists_local_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_workbench_overrides_do_not_use_app_mongo -v
```

结果：通过。
