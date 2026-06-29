# Canonical Facts Wave 5: Direct OA Mongo Legacy Bootstrap Removal

日期：2026-06-28

## 目标

删除 `server.py` 中 legacy bootstrap 时直接构造 `MongoOAAdapter` 的旧 App Mongo source path，避免生产 app/API 初始化链路保留 App Mongo fallback。

## 变更

- 删除 `Application._build_legacy_direct_oa_mongo_adapter(...)`。
- `_initialize_runtime_services(...)` 默认 `source_oa_adapter = None`。
- 正常 OA 读取仍只通过 `PostgresOAProjectionAdapter`，当 state store 暴露 `oa_projection_repository` 时启用。
- `_oa_pending_payment_source_adapter(...)` 保持独立外部输入路径，不复用 legacy bootstrap adapter。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 中 `server.py` 的 `MongoOAAdapter` removal baseline 从 11 降到 8。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter -v
```

结果：通过。

## Closure 状态

本 slice 删除了 direct OA Mongo legacy bootstrap builder。`MongoOAAdapter` 仍保留在 production app/worker 中作为外部 OA source/admission 路径，尤其是 OA pending payment source adapter 和 worker sync；这些不是 App canonical facts fallback，但仍需最终 audit 证明它们只通过 owner/admission 边界进入 PostgreSQL canonical facts。
