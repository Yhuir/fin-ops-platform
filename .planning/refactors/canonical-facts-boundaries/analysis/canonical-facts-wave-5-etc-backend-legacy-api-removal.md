# Wave 5 - ETC backend legacy batch API removal

日期：2026-06-28

## 目标

删除 backend legacy `/api/etc/batches*` 兼容 API。前端已迁移到 business-batches 和 canonical invoice list 后，该旧 API 不再有生产保留理由。

## 变更

- 删除 `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`。
- 删除：
  - `backend/src/fin_ops_platform/services/etc_legacy_batch_read_facade.py`
  - `backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py`
  - `backend/src/fin_ops_platform/services/etc_legacy_batch_lifecycle_service.py`
- `server.py` 删除：
  - legacy ETC batch route import 和 dispatch；
  - readiness legacy entrypoints；
  - `FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API` gate；
  - `_etc_legacy_batch_*` factories；
  - `_handle_legacy_etc_batch_business_delete(...)` shim。
- 删除 `tests/test_etc_legacy_batch_*` service tests。
- `tests/test_etc_backend.py` 删除直接保护 `/api/etc/batches*` 的旧 API tests；保留 reconciliation-backed OA draft 补充凭证测试并改用 `/api/etc/business-batches/{id}/oa-draft`。
- `tests/test_platform_runtime_boundary_guards.py` 将旧 gate/route-owner guard 改成 backend API removal guard。

## 边界结论

- `/api/etc/batches*` 不再是 app/API production wiring 的可达入口。
- `FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API` 不再是兼容开关；重新引入会被 static guard 拦截。
- ETC 页面和 backend 回归都通过 business-batches、reconciliation-tasks、invoice list 和 import routes 覆盖现有业务主链路。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_etc_batch_backend_api_is_removed tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_web_etc_api_does_not_call_legacy_batch_mutations_or_list tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
```

结果：通过；`tests.test_etc_backend` 118 个测试通过，4 个依赖本地票根样例的测试按既有 skip 条件跳过。

## 剩余

- 旧文档历史记录仍可保留为实施记录，不作为当前架构事实源。
- ETC historical repair/backfill tools 仍需按 tool-only owner/dry-run/deletion criteria 单独收口；它们不是 `/api/etc/batches*` production API。
