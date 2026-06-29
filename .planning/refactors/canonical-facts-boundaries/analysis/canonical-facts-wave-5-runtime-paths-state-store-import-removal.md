# Canonical Facts Wave 5 - runtime paths state-store import removal

日期：2026-06-29

## 目标

生产 app/worker/service/tool 不再为了默认数据目录 import local `state_store.py`，避免本地 `ApplicationStateStore` 模块继续出现在生产链路依赖图中。

## 变更

- 新增 `backend/src/fin_ops_platform/services/runtime_paths.py::default_data_dir()`。
- `backend/src/fin_ops_platform/services/state_store.py`
  - 删除自身 `default_data_dir()` 定义。
  - `ApplicationStateStore` 内部改用 `runtime_paths.default_data_dir` 的 private alias。
- 改为从 `runtime_paths` import `default_data_dir()`：
  - `backend/src/fin_ops_platform/app/main.py`
  - `backend/src/fin_ops_platform/app/worker.py`
  - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
  - `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`
  - `backend/src/fin_ops_platform/tools/repair_no_oa_bank_batch_lifecycle.py`
  - `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`
  - `tests/test_state_store.py`
- 新增 guard：
  - `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_production_runtime_paths_do_not_import_local_state_store`

## 边界结论

- `state_store.py` 仍是 local tooling/test store 的实现文件。
- 生产 app/worker/service/tool 不再从 `state_store.py` import helper。
- 该 slice 不删除 `ApplicationStateStore` 本体；它仍是 deferred local tooling/test I/O。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_paths.py backend/src/fin_ops_platform/services/state_store.py backend/src/fin_ops_platform/app/main.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/services/etc_reconciliation_service.py backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py backend/src/fin_ops_platform/tools/repair_no_oa_bank_batch_lifecycle.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_default_data_dir_honors_environment_override tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_runtime_paths_do_not_import_local_state_store tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_services_do_not_type_bind_to_local_application_state_store tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_local_state_store_does_not_expose_legacy_mongo_settings_loader
```

结果：通过。
