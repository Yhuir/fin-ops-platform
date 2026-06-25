# server-py:bank-details-category-write-route-callback-collapse

日期：2026-06-25

## 结论

`server-py:bank-details-category-write-route-callback-collapse` 已完成为 `local-implementation-closed`。

本 slice 将银行明细 category confirmation/assignment HTTP mapping 从 `server.py` 迁入 `BankDetailsApiRoutes.route(...)`：

- `POST /api/bank-details/transactions/{transaction_id}/category-confirmation`
- `DELETE /api/bank-details/transactions/{transaction_id}/category-confirmation`
- `POST /api/bank-details/transactions/{transaction_id}/category-assignment`
- `DELETE /api/bank-details/transactions/{transaction_id}/category-assignment`

`server.py` 不再定义：

- `_handle_api_bank_detail_category_confirmation`
- `_handle_api_bank_detail_category_confirmation_delete`
- `_handle_api_bank_detail_category_assignment`
- `_handle_api_bank_detail_category_assignment_delete`

## 实现摘要

- `BankDetailsApiRoutes.route(...)` 现在覆盖 bank-details read/export、auto-tag write 和 category write route mapping。
- route owner 负责 transaction id extraction 和 `unquote(...)`。
- category POST 继续通过 JSON body port 解析 payload；DELETE 不解析 body。
- route owner 在解析 body 前保持权限 precheck，保留原有 403 优先级。
- category validation、audit、dirty/outbox、derived lifecycle 和 side-effect port 仍由 `BankDetailsApplicationService` 负责。

## 边界说明

本 slice 不改变银行明细业务规则、read model refresh/dirty/outbox/lifecycle owner、前端 API shape、生产数据或生产服务。

## 测试和 Guard

新增/更新：

- `tests/test_bank_details_routes.py::BankDetailsRoutesTests::test_route_owner_handles_category_write_mapping_with_transaction_id_and_body_ports`
- `tests/test_bank_auto_tag_rules_api.py` category confirmation 测试改用 public `handle_request(...)` 边界。
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary` 更新为所有 bank-details write callbacks 都在 route owner。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
```

## 下一步

下一边界选择：`server-py:bank-details-route-owner-local-closure-audit`。

该 audit 应证明 `server.py` 不再定义任何 `_handle_api_bank_details*` / `_handle_api_bank_detail_category*` route callback，并分类剩余 bank-details `Application` surfaces。

## 未测风险

- 尚未运行完整 backend discover、frontend Vitest、Browser e2e 或生产验证。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行。
- 本 slice 不声明 bank-details module/global closure。
