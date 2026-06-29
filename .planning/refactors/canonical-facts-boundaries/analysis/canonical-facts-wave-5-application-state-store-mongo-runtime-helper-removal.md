# Wave 5 - ApplicationStateStore Mongo runtime/helper removal

日期：2026-06-29

## Scope

本切片删除 `ApplicationStateStore` 中剩余 App Mongo/GridFS runtime 字段、retry/helper、collection helper、GridFS import-file 分支和 fake Mongo state-store tests。

不修改 07-owned read model runtime 文件，不改变 PostgreSQL canonical facts owner。

## Boundary

- `ApplicationStateStore`：local pickle/JSON/file tooling-test store。
- PostgreSQL owner repositories：生产 canonical facts 唯一真相。
- `load_mongo_state_settings(...)`：仅保留配置解析 utility，不再被 `ApplicationStateStore` runtime 使用。

## I/O

保留输入/输出：

- local pickle：state、pending invoice commands、no-OA batches、app health alerts。
- local JSON：OA attachment invoice cache。
- local file：import file content。

删除的旧 I/O：

- App Mongo detailed collections。
- Mongo retry operation wrapper。
- GridFS import file upload/download/delete。
- fake Mongo state-store test harness。

## Validation

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_store_import_file_round_trips_locally tests.test_state_store.StateStoreTests.test_pending_invoice_commands_persist_locally tests.test_state_store.StateStoreTests.test_oa_attachment_invoice_cache_save_load_and_clear_locally tests.test_state_store.StateStoreTests.test_save_no_oa_bank_batches_persists_and_loads_local_snapshot tests.test_state_store.StateStoreTests.test_app_health_alerts_save_and_load_local_snapshot
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_import_matching_snapshots_do_not_use_app_mongo
```

结果：通过。

## Remaining

08 仍处于 `wave-5-code-removal`。剩余旧路径应继续按 bounded slice 删除；GridFS production worker 删除仍受 07-owned worker registry 协调限制。
