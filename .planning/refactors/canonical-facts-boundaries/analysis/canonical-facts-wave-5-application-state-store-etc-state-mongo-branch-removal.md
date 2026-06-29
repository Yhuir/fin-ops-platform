# Wave 5 - ApplicationStateStore ETC state Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 ETC 业务状态和 ETC reconciliation 状态读写的旧 App Mongo branch，避免 local tooling/test store 继续携带第二事实源路径。

## 变更

- `load_etc_state(...)` / `save_etc_state(...)` 不再读写 `_mongo_detailed_collections["etc_state"]`。
- `load_etc_reconciliation_state(...)` / `save_etc_reconciliation_state(...)` 不再读写 `_mongo_detailed_collections["etc_reconciliation_state"]`。
- 以上四个方法不再检查 `MONGO_ONLY_STORAGE_MODE`；`ApplicationStateStore` 在本轮 closure 中已经固定为 local-pickle tooling/test store，production canonical facts 由 PostgreSQL owner repository 和 `PostgresStateStore` 管理。
- 新增 static guard 禁止这些方法重新引用 `_mongo_database`、`_mongo_detailed_collections` 或 `MONGO_ONLY_STORAGE_MODE`。
- 新增本地 round-trip 测试证明 ETC state 和 reconciliation state 仍可跨 store instance 持久化。

## 边界结论

- 本 slice 不改变 `ApplicationStateStoreProtocol`。
- 本 slice 不修改 PostgreSQL canonical facts owner repository。
- 本 slice 不修改 read model / worker runtime 文件，遵守 07 read-model controller 文件隔离。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_etc_states_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_etc_states_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
