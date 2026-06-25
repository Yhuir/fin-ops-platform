# server-py:turnover-ledger-closure-withdraw-route-callback-collapse

日期：2026-06-25

## 结论

`POST /api/turnover-ledger/closures/withdraw` 的 HTTP mapping 已从 `server.py` 迁入 `TurnoverLedgerApiRoutes.route(...)`。

`server.py` 不再定义：

- `_handle_api_turnover_ledger_closure_withdraw(...)`

其他 turnover ledger mutation callback 保持不变：

- `_handle_api_turnover_ledger_withdraw(...)`

## 实现

`TurnoverLedgerApiRoutes.route(...)` 新增 `POST /api/turnover-ledger/closures/withdraw` 分支，调用：

- `handle_closure_withdraw_route(...)`

复用显式端口：

- `closure_request_boundary_provider`
- `mutation_session_resolver`
- `session_error_detector`
- `load_json_body`
- `tenant_id_provider`
- `write_precondition_error_payload`

`closure_request_boundary_provider` 由 `Application` 通过 lambda 注入：

- `closure_request_boundary_provider=lambda: self._turnover_ledger_closure_request_boundary_facade()`

使用 lambda 是为了保留原 app callback 的动态 provider override 语义；现有测试会在 app 构建后替换 `_turnover_ledger_closure_request_boundary_facade`，route owner 必须仍能读取替换后的 boundary。

Route owner 仍不 import `app.auth`，不读取 cookie/header 细节，不接收 whole `Application`。

## 行为保持

保持原 HTTP 行为：

- mutation permission 失败仍返回原 session resolver response；
- invalid JSON/body 仍返回 `_load_json_body(...)` 的错误 response；
- `cash_closure_case_id` / `cashClosureCaseId` 兼容保留；
- actor fallback 仍为 `username -> user_id -> web_finance_user`；
- tenant 仍由 `tenant_id_for_session(...)` port 提供；
- `idempotency_key` / `idempotencyKey` 兼容保留；
- closure request boundary 继续负责 cash closure case withdraw、Workbench relation command service、idempotency 和 refresh side effects；
- `TurnoverRelationValidationError` 继续映射 400 并保留 `error_code`；
- `TurnoverLedgerWritePreconditionError` 继续通过 `write_precondition_error_payload` 生成 response payload；
- `WorkbenchIdempotency*` 继续映射 409；
- 成功 response shape 不变。

## 测试和 Guard

更新：

- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_closure_withdraw_handler_uses_closure_boundary_without_relation_withdraw_inline`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

Guard 现在证明：

- `TurnoverLedgerApiRoutes` 拥有 closure withdraw route-owner 方法；
- `server.py` 不再定义 `_handle_api_turnover_ledger_closure_withdraw(...)`；
- relation withdraw callback 仍保留在 `server.py`；
- `server.py` 注入 closure request-boundary port，并保留动态 provider override。

计划验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_closure_withdraw_handler_uses_closure_boundary_without_relation_withdraw_inline tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_cash_closure_withdraw_route_uses_closure_boundary tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

## 七类测试适用性

1. Business core unit tests：不适用；未改 withdraw cash closure case 的业务规则。
2. Service-layer tests：适用但未新增；closure request boundary/write facade/UoW 既有回归继续覆盖 Workbench relation command service wiring、idempotency 和 refresh side effects。
3. API contract tests：适用；复跑 closure withdraw targeted regressions 和完整 `tests.test_turnover_ledger_api`，覆盖 cash closure case id 兼容、provider override、response shape 和 closure/withdraw wiring。
4. Read model/cache/background job tests：间接受影响；closure withdraw 成功后的 refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
5. Frontend component and interaction tests：不适用；未改前端 API mapper、toolbar withdraw UI 或 operation overlay。
6. End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移 HTTP mapping，不改变 closure withdraw business flow。
7. Existing feature regression tests：适用；更新 platform Guard 防止 closure withdraw callback 回到 `server.py`，并确认 relation withdraw callback 未被误删。

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- relation withdraw callback 仍待迁移。

## 下一步

选择 `server-py:turnover-ledger-relation-withdraw-route-callback-collapse`，单独迁移 `POST /api/turnover-ledger/relations/{relation_id}/withdraw`。
