# Wave 5 - ApplicationStateStore workbench pair relations Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 workbench pair relations 的旧 App Mongo 分支。

## 变更

- `load_workbench_pair_relations(...)` / `save_workbench_pair_relations(...)` 只保留本地 pickle I/O。
- 删除该组方法中的 `_mongo_database` / `MONGO_ONLY_STORAGE_MODE` 分支。
- 将旧 Mongo-specific tests 收敛为本地 store round-trip / changed-case merge 测试。
- 新增 static guard 禁止这组方法重新接入 App Mongo。

## 边界结论

- 生产 workbench pair relation facts 仍由 PostgreSQL workbench relation repository 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_workbench_pair_relations_persists_and_loads_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_pair_relations_can_incrementally_update_changed_case_only tests.test_state_store.StateStoreTests.test_save_workbench_pair_relations_persists_history_metadata -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_workbench_pair_relations_do_not_use_app_mongo -v
```

结果：通过。
