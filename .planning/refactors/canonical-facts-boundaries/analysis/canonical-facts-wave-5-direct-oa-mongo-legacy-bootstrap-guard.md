# Canonical Facts Wave 5: Direct OA Mongo Legacy Bootstrap Guard

日期：2026-06-28

## Scope

锁定 `server.py` 中 direct `MongoOAAdapter` 只能作为 explicit legacy bootstrap 路径，不能回到 production API bootstrap 或普通页面 source-of-truth fallback。

## Changes

- `tests/test_platform_runtime_boundary_guards.py`
  - 新增 `test_server_direct_oa_mongo_adapter_is_legacy_bootstrap_only`。
  - 要求 `_build_legacy_direct_oa_mongo_adapter()` 保持 `bootstrap_mode == "legacy"` gate。
  - 要求 `_initialize_runtime_services(...)` 只通过 legacy-only builder 设置 `_source_oa_adapter`。
  - 禁止 `_oa_pending_payment_source_adapter()` 复用 legacy bootstrap adapter。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_direct_oa_mongo_adapter_is_legacy_bootstrap_only tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter -v
```

结果：通过。

## Closure Note

本 slice 没有删除 `MongoOAAdapter`。OA Mongo 仍是外部输入/同步来源；direct adapter 的 legacy bootstrap 使用仍保留为 deferred，不计为 final closure。当前证据只证明它不会进入 production bootstrap source-of-truth 链路。
