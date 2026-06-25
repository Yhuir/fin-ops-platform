# server-py:bank-details-read-export-route-callback-collapse

日期：2026-06-25

## 结论

`server-py:bank-details-read-export-route-callback-collapse` 已完成为 `local-implementation-closed`。

本 slice 将银行明细 read/export HTTP mapping 从 `server.py` 迁入 `BankDetailsApiRoutes.route(...)`：

- `GET /api/bank-details/accounts`
- `GET /api/bank-details/transactions`
- `GET /api/bank-details/transactions/export`
- `GET /api/bank-details/auto-tag-rules`

`server.py` 不再定义对应 read/export callbacks：

- `_handle_api_bank_details_accounts`
- `_handle_api_bank_details_auto_tag_rules`
- `_handle_api_bank_details_transactions`
- `_handle_api_bank_details_transactions_export`

## 实现摘要

- `BankDetailsApiRoutes` 增加 `route(...)`，负责上述 read/export path matching、query extraction、read-session auth resolution、JSON response 和 export response delegation。
- `Application._bank_details_routes()` 显式注入 `resolve_read_session`、`json_response`、`export_response`。
- `server.py` 对 `/api/bank-details/...` 先委托 `self._bank_details_routes().route(...)`；未命中的写入路径继续走现有写入 callbacks。
- 保留银行明细写入 callbacks，等待后续专门 slice：auto-tag PUT/reapply/file-replacement 和 category confirmation/assignment。

## 边界说明

本 slice 不改变银行明细业务规则、read model freshness、dirty scope、outbox、cache、worker、自动标签写入、分类写入 side effects、前端 API shape 或生产数据。

## 测试和 Guard

新增/更新：

- `tests/test_bank_details_routes.py::BankDetailsRoutesTests::test_route_owner_handles_read_and_export_http_mapping_with_platform_ports`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_read_export_routes_use_route_owner`
- 更新旧测试调用点，避免继续依赖删除后的 app callbacks：
  - `tests/test_bank_auto_tag_rules_api.py`
  - `tests/test_runtime_bootstrap.py`

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_get_returns_system_active_archived_fields_and_permissions tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_transactions_do_not_fallback_to_legacy_service tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_accounts_do_not_fallback_to_legacy_service tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_postgres_bank_details_accounts_missing_balance_table_returns_refreshing -v
```

## 下一步

下一边界选择：`server-py:bank-details-write-route-callback-audit`。

原因：银行明细 write callbacks 仍在 `server.py`，但权限、JSON body、file source、side-effect lifecycle 和 dirty/outbox 风险更高，应先单独审计，再拆成一个或多个写入迁移 slice。

## 未测风险

- 尚未运行完整 bank details 后端回归、前端 Vitest、Browser e2e 或生产验证。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行。
- 本 slice 不声明 bank-details module/global closure。
