# Canonical Facts Wave 5 - ApplicationStateStore ETC GridFS Branch Removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` ETC reconciliation/invoice file 路径里已不可达的 Mongo GridFS 分支。`ApplicationStateStore` 已不再构造 Mongo bucket，因此这些分支只能保留旧事实源污染面。

## 变更

- `store_etc_reconciliation_file(...)` 只写本地文件。
- `read_etc_reconciliation_file("gridfs://...")` 直接失败。
- `store_etc_invoice_file(...)` 只写本地文件。
- `read_etc_invoice_file("gridfs://...")` 直接失败。
- `etc_invoice_file_exists("gridfs://...")` 返回 `False`。
- `delete_etc_invoice_file("gridfs://...")` no-op。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_application_state_store_etc_file_paths_do_not_use_mongo_gridfs`。
- 新增 `tests/test_state_store.py::StateStoreTests.test_etc_files_persist_locally_and_reject_legacy_gridfs_refs`。

## 边界结论

- 本 slice 不删除 `ApplicationStateStore` local pickle 本体。
- 本 slice 不删除 `PostgresStateStore` / GridFS migration worker path。
- `file_object.gridfs_migration` worker 删除仍受 07-owned registry 阻塞。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_etc_files_persist_locally_and_reject_legacy_gridfs_refs -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_etc_file_paths_do_not_use_mongo_gridfs tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
