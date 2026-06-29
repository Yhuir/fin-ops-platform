# Canonical Facts Wave 5 - ApplicationStateStore Settings/OA Mongo Branch Removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` settings、OA attachment cache、OA sync state、manual OA imports 方法里的不可达 App Mongo branch。

## 变更

- `load_app_settings(...)` / `save_app_settings(...)` 只使用本地 JSON 文件。
- `load_oa_attachment_invoice_cache_entry(...)` / `save_oa_attachment_invoice_cache_entry(...)` 只使用本地 JSON 文件。
- `load_oa_sync_state(...)` / `save_oa_sync_state(...)` 只使用本地 pickle 文件。
- `load_manual_oa_imports(...)` / `save_manual_oa_imports(...)` 只使用本地 JSON 文件。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_application_state_store_settings_and_oa_cache_do_not_use_app_mongo`。

## 边界结论

- 本 slice 不删除 `ApplicationStateStore` local pickle 本体。
- 本 slice 不删除 OA Mongo external source adapter；OA Mongo 仍是外部输入边界，不是 App Mongo snapshot store。
- `load_mongo_state_settings(...)` 暂时保留给 GridFS legacy reader。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_settings_and_oa_cache_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_local_manual_oa_imports_are_persisted_idempotently_and_removable tests.test_state_store.StateStoreTests.test_oa_attachment_invoice_cache_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_oa_sync_state_persists_locally_across_store_instances -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
