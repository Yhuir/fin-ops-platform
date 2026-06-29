# Canonical Facts Wave 5 - ApplicationStateStore App Mongo Construction Removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 自动接入 App Mongo snapshot 的构造入口。`ApplicationStateStore` 仍作为 local pickle tooling/test store 存在，但不再读取 `app_mongo_config.json` 或 `FIN_OPS_STORAGE_MODE=mongo_only` 来把 App Mongo 变成事实源。

## 变更

- `ApplicationStateStore.__init__(...)` 不再调用 `load_mongo_state_settings(...)`。
- `ApplicationStateStore.__init__(...)` 不再构造 `MongoClient` / `GridFSBucket`。
- `storage_backend` / `storage_mode` 固定为 `local_pickle`；`mongo_database_name` 固定为 `None`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source`。
- 更新 `tests/test_state_store.py::StateStoreTests.test_application_state_store_ignores_app_mongo_config`，证明 local store 忽略 `app_mongo_config.json`。

## 边界结论

- `load_mongo_state_settings(...)` 暂时保留给 `LegacyGridFSFileReader` / GridFS worker path；该 worker 删除仍受 07-owned registry 阻塞。
- 本 slice 未删除 `ApplicationStateStore` local pickle 本体；local pickle 仍是后续删除/隔离项。
- 本 slice 未清空所有已不可达的 Mongo branch method body；后续可单独删除 stale Mongo methods/tests。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_application_state_store_ignores_app_mongo_config tests.test_state_store.StateStoreTests.test_local_manual_oa_imports_are_persisted_idempotently_and_removable tests.test_state_store.StateStoreTests.test_save_no_oa_bank_batches_persists_and_loads_local_snapshot tests.test_state_store.StateStoreTests.test_oa_attachment_invoice_cache_persists_locally_across_store_instances -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
