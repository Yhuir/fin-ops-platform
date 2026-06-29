# Canonical Facts Wave 5: Local Pickle Deploy Guard

日期：2026-06-28

## Slice

锁定生产部署模板不能把 app runtime 重新配置为 local pickle / non-PostgreSQL source-of-truth。

## Evidence

- `Application.readiness_summary()` 已在 production runtime guard 下拒绝非 PostgreSQL storage backend。
- `deploy/oa/env/fin-ops.common.env.example` 当前设置 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
- release env examples 当前没有把 `FIN_OPS_APP_STORAGE_BACKEND` 设为 `local_pickle`、`mongo_only` 或其它旧 backend。

## Change

- `tests/test_platform_runtime_boundary_guards.py`
  - 新增 `test_deploy_runtime_templates_keep_app_storage_backend_postgres`。
  - 扫描 `deploy/oa/env/*.env.example` 和 `deploy/oa/fin_ops.env.example`。
  - 如果出现 `FIN_OPS_APP_STORAGE_BACKEND=`，值必须是 `postgres`。
  - 要求 common env template 显式保留 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_deploy_runtime_templates_keep_app_storage_backend_postgres -v
```

结果：通过。

## Closure Note

本 slice 未删除 `ApplicationStateStore` / local pickle implementation。它们仍可能服务 dev/test/tooling。生产 closure 先通过 readiness guard + deploy template guard 阻断正常 API/worker 入口；最终删除或工具隔离仍需单独 owner-migration slice。
