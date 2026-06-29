# Wave 5 - ApplicationStateStore jobs and health Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 background jobs 和 app health alerts 的旧 App Mongo 分支，避免 local tooling/test store 继续保留第二事实源。

## 变更

- `load_background_jobs(...)` / `save_background_jobs(...)` 不再读写 Mongo detailed collection。
- `load_app_health_alerts(...)` / `save_app_health_alerts(...)` 不再读写 Mongo detailed collection。
- 以上方法不再检查 `MONGO_ONLY_STORAGE_MODE`。
- 新增 static guard 和本地 round-trip 测试。

## 边界结论

- 本 slice 不改变 `ApplicationStateStoreProtocol`。
- 本 slice 不修改 `PostgresStateStore` 或 PostgreSQL canonical facts owner repository。
- 本 slice 不修改 read model / worker runtime 文件，遵守 07 read-model controller 文件隔离。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_background_jobs_persist_locally_across_store_instances tests.test_state_store.StateStoreTests.test_app_health_alerts_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_jobs_and_health_do_not_use_app_mongo -v
```

结果：通过。
