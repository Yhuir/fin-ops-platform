# server-py:bank-details-auto-tag-write-route-callback-collapse

日期：2026-06-25

## 结论

`server-py:bank-details-auto-tag-write-route-callback-collapse` 已完成为 `local-implementation-closed`。

本 slice 将银行明细 auto-tag 写入口 HTTP mapping 从 `server.py` 迁入 `BankDetailsApiRoutes.route(...)`：

- `PUT /api/bank-details/auto-tag-rules`
- `POST /api/bank-details/auto-tag-rules/reapply`
- `POST /api/bank-details/auto-tag-rules/file-replacement`

`server.py` 不再定义：

- `_handle_api_bank_details_auto_tag_rules_update`
- `_handle_api_bank_details_auto_tag_rules_reapply`
- `_handle_api_bank_details_auto_tag_rules_file_replacement`

## 实现摘要

- `BankDetailsApiRoutes.route(...)` 现在覆盖 auto-tag GET/read 和 PUT/reapply/file-replacement write mapping。
- `Application._bank_details_routes()` 显式注入：
  - `resolve_read_session`
  - `json_response`
  - `export_response`
  - `load_json_body`
  - `default_auto_tag_rules_source_provider`
- route owner 在解析 body 前保持权限 precheck，保留原有 403 优先级。
- file replacement 空 body 继续通过 bundled normalized rules source provider 获取默认规则。
- PUT/reapply/file-replacement 的业务、audit、dirty/outbox、derived lifecycle 仍由 `BankDetailsApplicationService` / `AppSettingsService` 承担。

## 边界说明

本 slice 不改变：

- 自动标签规则业务合同；
- read model refresh/dirty/outbox/lifecycle owner；
- category confirmation/assignment 写入口；
- 前端 API shape；
- 生产数据或生产服务。

## 测试和 Guard

新增/更新：

- `tests/test_bank_details_routes.py::BankDetailsRoutesTests::test_route_owner_handles_auto_tag_write_mapping_with_body_and_default_source_ports`
- `tests/test_bank_auto_tag_rules_api.py` 改用 public `handle_request(...)` 边界验证 PUT/file-replacement。
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary` 更新为 auto-tag write route-owner + category callbacks retained。

## 验证命令

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_bank_auto_tag_rules_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner -v
```

## 下一步

下一边界选择：`server-py:bank-details-category-write-route-callback-collapse`。

该 slice 应只迁移 category confirmation/assignment POST/DELETE route mapping，并保留 transaction id extraction、permission denial、body parsing 和 category validation error mapping。

## 未测风险

- 尚未运行完整 backend discover、frontend Vitest、Browser e2e 或生产验证。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行。
- 本 slice 不声明 bank-details module/global closure。
