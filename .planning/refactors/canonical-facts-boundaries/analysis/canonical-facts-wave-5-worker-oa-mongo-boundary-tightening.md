# Canonical Facts Wave 5: Worker OA Mongo Boundary Tightening

日期：2026-06-28

## Scope

收紧 `backend/src/fin_ops_platform/app/worker.py` 对 direct `MongoOAAdapter` 的依赖，避免 worker 里的非同步入口继续携带旧 adapter 类型耦合。

## Changes

- `_no_oa_workbench_matching_source_versions(...)` 改用 `attachment_invoice_cache_parser_version()`，不再通过 `MongoOAAdapter` 读取 parser version。
- worker 内部缓存和 `_oa_payment_source_adapter()` 的类型标注改为 `Any | None`，删除不必要的 direct adapter 类型暴露。
- `MongoOAAdapter(...)` direct construction 只保留在 `_build_oa_sync_source_adapter(...)`。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 将 `backend/src/fin_ops_platform/app/worker.py` 的 `MongoOAAdapter` baseline 从 6 降到 2。
- 新增 `test_worker_oa_mongo_adapter_is_confined_to_sync_source_factory`，禁止 worker 重新通过 `MongoOAAdapter._attachment_invoice_cache_parser_version` 或多个构造点引入旧 adapter 依赖。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/worker.py tests/test_platform_runtime_boundary_guards.py tests/test_worker_oa_sync.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_mongo_adapter_direct_use_is_allowlisted tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_worker_oa_mongo_adapter_is_confined_to_sync_source_factory -v
PYTHONPATH=backend/src python3 -m unittest tests.test_worker_oa_sync -v
```

Result: passed.

## Remaining

OA Mongo sync worker 本身仍是外部 OA 输入到 PostgreSQL `app.oa_*` projection facts 的 admission/sync 边界，不是本 slice 删除对象。Final canonical facts closure 仍不能把它算作完成：后续必须把该入口迁到明确的外部输入边界合同，或在生产不再需要时删除 direct adapter construction。
