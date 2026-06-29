# Canonical Facts Wave 5: ETC Legacy API Production Gate

日期：2026-06-28

## 目标

阻断 legacy `/api/etc/batches*` 在 production runtime guard 下继续作为 ETC canonical facts 的生产入口。

## 当前判断

- `/api/etc/batches*` 仍被前端 `web/src/features/etc/api.ts` 和大量后端回归测试使用。
- 直接删除该 route 会变成前后端 API 迁移，不适合作为本 slice 的最小安全改动。
- 该 route 仍是旧兼容入口，不能算 canonical facts closure。

## 变更

- `Application._handle_request_untracked(...)` 的 legacy ETC batch dispatch 现在必须经过 `_legacy_etc_batch_api_enabled()`。
- `_legacy_etc_batch_api_enabled()` 规则：
  - `FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API=1/true/yes/on`：显式启用。
  - `FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API=0/false/no/off`：显式禁用。
  - 未设置时，`FIN_OPS_PRODUCTION_RUNTIME_GUARD=1` 下默认禁用；非 production guard 下保持本地/测试兼容。
- `readiness_summary().entrypoints` 在 legacy gate 关闭时不再列出 `/api/etc/batches*`。
- static guard 要求 dispatch 保持 gate，并禁止生产 deploy env templates 设置 `FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API`。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_etc_batch_api_is_gated_under_production_guard tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_routes_delegate_to_compat_route_owner -v
```

结果：通过。

## Closure 状态

本 slice 是 production gate，不是最终删除。legacy `/api/etc/batches*` 仍是 `pending-removal`：下一步需要把前端和后端测试迁移到 `/api/etc/business-batches*` / reconciliation task / import owner API 后，删除 `routes_etc_legacy_batches.py`、`etc_legacy_batch_*` 兼容服务和相关旧测试。
