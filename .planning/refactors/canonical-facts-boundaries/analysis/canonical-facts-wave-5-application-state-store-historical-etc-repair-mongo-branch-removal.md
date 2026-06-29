# Wave 5 - ApplicationStateStore historical ETC repair Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 historical ETC repair bundle / parsed seed / repair state 的旧 App Mongo 和 GridFS 分支，避免 local tooling/test store 继续保留第二事实源。

## 变更

- `save_historical_etc_repair_bundle(...)` 不再写 Mongo GridFS 或 `historical_etc_repair_bundles` detailed collection。
- `load_historical_etc_repair_bundle_metadata(...)` 不再读 Mongo detailed collection。
- `read_historical_etc_repair_bundle(...)` 对旧 `gridfs://` bundle metadata 明确失败。
- `save_historical_etc_repair_parsed_seed(...)` / `load_historical_etc_repair_parsed_seeds(...)` 不再读写 Mongo detailed collection。
- `load_historical_etc_repair_states(...)` / `save_historical_etc_repair_states(...)` 不再读写 Mongo detailed collection。
- 删除 historical ETC repair GridFS id helper。
- 新增 static guard 和本地 round-trip 测试。

## 边界结论

- 本 slice 不改变 `ApplicationStateStoreProtocol`。
- 本 slice 不修改 `PostgresStateStore` 或 PostgreSQL canonical facts owner repository。
- 本 slice 不修改 read model / worker runtime 文件，遵守 07 read-model controller 文件隔离。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_historical_etc_repair_persists_locally_and_rejects_legacy_gridfs_refs -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_historical_etc_repair_does_not_use_app_mongo -v
```

结果：通过。
