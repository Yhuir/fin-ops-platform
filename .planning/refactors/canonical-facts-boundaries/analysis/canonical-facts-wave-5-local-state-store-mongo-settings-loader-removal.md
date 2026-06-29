# Canonical Facts Wave 5 - local state store Mongo settings loader removal

日期：2026-06-29

## 目标

移除 local `ApplicationStateStore` 模块中的 legacy App Mongo settings loader，避免本地 pickle/test store 继续携带 App Mongo snapshot 配置入口。

## 变更

- `backend/src/fin_ops_platform/services/state_store.py`
  - 删除 `MongoStateSettings`。
  - 删除 `load_mongo_state_settings(...)`。
  - 删除 `DEFAULT_APP_MONGO_DATABASE` 和 `quote_plus` 依赖。
- `backend/src/fin_ops_platform/services/file_object_migration.py`
  - 新增 `LegacyGridFSMongoSettings`。
  - 新增 `load_legacy_gridfs_mongo_settings(...)`。
  - `LegacyGridFSFileReader.from_data_dir(...)` 改为读取迁移边界内的 legacy GridFS Mongo config。
- `tests/test_state_store.py`
  - 将 legacy App Mongo config 测试从 `state_store` 挪到 file-object migration boundary。
- `tests/test_platform_runtime_boundary_guards.py`
  - 新增 guard，防止 `state_store.py` 重新暴露 `MongoStateSettings` / `load_mongo_state_settings`。

## 边界结论

- `ApplicationStateStore` 继续只是 local tooling/test I/O，不再知道 App Mongo settings loader。
- GridFS 迁移 worker 仍是 legacy migration boundary；它保留 legacy Mongo 读取能力，但不再通过 local state store 暴露。
- 完整删除 `file_object.gridfs_migration` 仍需要同时修改 07-owned `runtime_worker_registry.py`，本 slice 不触碰。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/file_object_migration.py backend/src/fin_ops_platform/services/state_store.py tests/test_state_store.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_legacy_gridfs_migration_uses_explicit_app_mongo_config_with_default_database tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_expose_legacy_gridfs_reader tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_local_state_store_does_not_expose_legacy_mongo_settings_loader tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline
rg -n "load_mongo_state_settings|MongoStateSettings" backend/src/fin_ops_platform -g '*.py'
rg -n "from fin_ops_platform\\.services\\.state_store import GRIDFS_REF_PREFIX|from fin_ops_platform\\.services\\.state_store import.*load_mongo" backend/src/fin_ops_platform -g '*.py'
```

结果：通过。两个 `rg` 扫描在 production code 中无命中。

## 剩余

- `file_object.gridfs_migration` production worker deletion remains `blocked-by-read-model-controller` until the 07 controller releases `backend/src/fin_ops_platform/services/runtime_worker_registry.py`.
