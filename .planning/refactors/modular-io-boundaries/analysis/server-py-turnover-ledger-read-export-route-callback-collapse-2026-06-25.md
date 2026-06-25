# server-py:turnover-ledger-read-export-route-callback-collapse

日期：2026-06-25

## 结论

`server.py` 不再拥有 `/api/turnover-ledger*` 的 read/export/GET HTTP callback 实现。

本 slice 已把以下 GET 路由的查询参数解析、HTTP 错误映射和 response 生成委托到 `TurnoverLedgerApiRoutes.route(...)`：

- `GET /api/turnover-ledger`
- `GET /api/turnover-ledger/export-preview`
- `GET /api/turnover-ledger/export`
- `GET /api/turnover-ledger/tag-selection`
- `GET /api/turnover-ledger/relations/{relation_id}`
- `GET /api/turnover-ledger/relations/{relation_id}/extra`

`server.py` 仍保留 turnover ledger mutation callbacks，作为下一轮 write-boundary audit 的明确待办：

- `_handle_api_turnover_ledger_tag_selection_update(...)`
- `_handle_api_turnover_ledger_bank_row_tags_batch(...)`
- `_handle_api_turnover_ledger_relation_extra_update(...)`
- `_handle_api_turnover_ledger_confirm(...)`
- `_handle_api_turnover_ledger_closure_confirm(...)`
- `_handle_api_turnover_ledger_closure_withdraw(...)`
- `_handle_api_turnover_ledger_withdraw(...)`

## 实现

### Route owner

`backend/src/fin_ops_platform/app/routes_turnover_ledger.py` 新增 `TurnoverLedgerApiRoutes.route(...)`，并把 GET HTTP wrapper 拆成 route-owner 方法：

- `handle_list_route(...)`
- `handle_export_preview_route(...)`
- `handle_export_route(...)`
- `handle_tag_selection_route(...)`
- `handle_relation_route(...)`
- `handle_relation_extra_route(...)`

这些方法继续调用既有 route/service 能力：

- `list_ledger(...)`
- `export_preview(...)`
- `export(...)`
- `get_relation(...)`
- `get_relation_extra(...)`

### 显式 I/O 端口

`TurnoverLedgerApiRoutes` 构造函数新增三个显式 platform ports：

- `json_response`
- `export_response`
- `tag_selection_provider`

`Application` 只负责组合这些端口：

- `json_response=self._json_response`
- `export_response=self._turnover_ledger_export_response`
- `tag_selection_provider=self._app_settings_service.get_turnover_ledger_tag_selection_payload`

导出 XLSX 的二进制 response 仍由 `Application._turnover_ledger_export_response(...)` 作为平台 adapter 提供；route owner 不直接构造 `Response`。

### server.py 收口

`Application.handle_request(...)` 对 `/api/turnover-ledger*` 先调用：

`self._turnover_ledger_api_routes.route(method, route_path, query)`

若 route owner 返回 `None`，再继续落到 PUT/POST mutation callbacks。已删除的 app-owned GET callbacks：

- `_handle_api_turnover_ledger(...)`
- `_handle_api_turnover_ledger_export_preview(...)`
- `_handle_api_turnover_ledger_export(...)`
- `_handle_api_turnover_ledger_relation(...)`
- `_handle_api_turnover_ledger_relation_extra(...)`
- `_handle_api_turnover_ledger_tag_selection(...)`
- `_turnover_ledger_query_value(...)`
- `_turnover_ledger_query_int(...)`

## 测试和 Guard

新增/更新：

- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`
- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_export_limit_returns_structured_error`

Guard 证明：

- `TurnoverLedgerApiRoutes` 拥有 read/export GET dispatch。
- `server.py` 不再定义迁移后的 read/export GET callbacks。
- mutation callbacks 仍保留在 `server.py`，没有被本 slice 顺手迁移。
- `server.py` 注入 `json_response`、`export_response`、`tag_selection_provider` 三个显式端口。

已运行验证：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_facade -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

结果：

- `tests.test_turnover_ledger_read_facade`: 2 tests passed。
- targeted platform runtime boundary guards: 2 tests passed。
- `tests.test_turnover_ledger_api`: 140 tests passed。

## 七类测试适用性

1. Business core unit tests：不适用；未改外部往来金额、标签准入、闭环、撤回或 extra 业务规则。
2. Service-layer tests：适用，复用 `tests/test_turnover_ledger_read_facade.py` 验证 read facade 仍代理到 route/service boundary。
3. API contract tests：适用，复跑 `tests/test_turnover_ledger_api.py`，覆盖列表/grouped/tag-selection/extra/export 和 mutation 回归。
4. Read model/cache/background job tests：间接受影响，API 回归覆盖 grouped read model metadata 和 stale refresh enqueue；本 slice 未改 worker、dirty/outbox 或 read model writer。
5. Frontend component and interaction tests：不适用；未改前端 API mapper 或页面交互。
6. End-to-end business-flow integration tests：不适用；未改 confirm/withdraw/tag-selection 写业务流。
7. Existing feature regression tests：适用，新增 platform Guard 防止 read/export GET callback 回到 `server.py`，并确认 mutation callbacks 保留。

## 未测风险

- 本 slice 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser 或生产写入验证。
- mutation callbacks 仍是下一轮待审计对象；不能据此声明 turnover ledger route-owner 或模块全局 closed。
- 真实导出大数据性能、真实 admin/write evidence 和生产 Browser evidence 仍属于最终验证范围。

## 下一步

选择 `server-py:turnover-ledger-write-route-callback-audit`，审计剩余 PUT/POST callbacks 是否可按 tag-selection、bank-row-tags、relation-extra、confirm/withdraw/closure withdraw 分组迁移，或需要先抽 service/request boundary。
