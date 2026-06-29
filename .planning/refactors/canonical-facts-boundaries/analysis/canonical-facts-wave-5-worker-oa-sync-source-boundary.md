# Wave 5 - Worker OA sync source boundary

日期：2026-06-28

## 目标

删除 `app/worker.py` 对 `MongoOAAdapter` 的直接 import 和 construction。OA Mongo 仍是外部 OA 输入源，但构造点必须归到 OA sync source boundary，不留在 app worker orchestration 层。

## 变更

- 新增 `services/oa_sync_source_adapter.py`，集中构造 OA sync source adapter。
- `app/worker.py` 改为调用 `build_oa_sync_source_adapter(...)`，不再 import 或直接构造 `MongoOAAdapter`。
- worker `MongoOAAdapter` removal baseline 从 2 降到 0。
- `test_oa_mongo_adapter_direct_use_is_allowlisted` 只允许 `services/oa_sync_source_adapter.py` 直接 import `MongoOAAdapter`。
- `test_worker_oa_mongo_adapter_is_confined_to_sync_source_boundary` 证明 worker 两条 OA sync path 都委托到边界。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/services/oa_sync_source_adapter.py tests/test_platform_runtime_boundary_guards.py tests/test_worker_oa_sync.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_mongo_adapter_direct_use_is_allowlisted tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_worker_oa_mongo_adapter_is_confined_to_sync_source_boundary tests.test_worker_oa_sync -v
```

结果：通过。

## 剩余

`MongoOAAdapter` 仍存在于 `services/oa_sync_source_adapter.py`，作为 OA 外部输入/admission 边界进入 PostgreSQL `app.oa_*` projection facts。它不再由 `app/server.py` 或 `app/worker.py` 直接构造。
