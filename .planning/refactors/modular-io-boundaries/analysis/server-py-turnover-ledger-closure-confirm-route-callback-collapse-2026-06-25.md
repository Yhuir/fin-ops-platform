# server-py:turnover-ledger-closure-confirm-route-callback-collapse

日期：2026-06-25

## 结论

`POST /api/turnover-ledger/closures/confirm` 的 HTTP mapping 已从 `server.py` 迁入 `TurnoverLedgerApiRoutes.route(...)`。

`server.py` 不再定义：

- `_handle_api_turnover_ledger_closure_confirm(...)`

其他 turnover ledger mutation callbacks 保持不变：

- `_handle_api_turnover_ledger_closure_withdraw(...)`
- `_handle_api_turnover_ledger_withdraw(...)`

## 实现

`TurnoverLedgerApiRoutes.route(...)` 新增 `POST /api/turnover-ledger/closures/confirm` 分支，调用：

- `handle_closure_confirm_route(...)`

新增显式端口：

- `closure_request_boundary_provider`

该端口由 `Application` 在组合根注入：

- `closure_request_boundary_provider=self._turnover_ledger_closure_request_boundary_facade`

Route owner 复用已有 mutation ports：

- `mutation_session_resolver`
- `session_error_detector`
- `load_json_body`
- `tenant_id_provider`
- `write_precondition_error_payload`

Route owner 仍不 import `app.auth`，不读取 cookie/header 细节，不接收 whole `Application`。

## 行为保持

保持原 HTTP 行为：

- mutation permission 失败仍返回原 session resolver response；
- invalid JSON/body 仍返回 `_load_json_body(...)` 的错误 response；
- `bank_row_ids` 缺失或非 array -> 400 `invalid_bank_row_ids`；
- actor fallback 仍为 `username -> user_id -> web_finance_user`；
- tenant 仍由 `tenant_id_for_session(...)` port 提供；
- `expected_versions` 仍只在 object 时传入，否则为空 dict；
- `idempotency_key` / `idempotencyKey` 兼容保留；
- closure request boundary 继续负责 affected-months、stale precondition、Workbench relation command service、write facade、idempotency 和 refresh side effects；
- `TurnoverRelationValidationError` 继续映射 400 并保留 `error_code`；
- `TurnoverLedgerWritePreconditionError` 继续通过 `write_precondition_error_payload` 生成 response payload；
- `WorkbenchIdempotency*` 继续映射 409；
- 成功 response shape 不变。

## 测试和 Guard

更新：

- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_closure_confirm_handler_delegates_affected_months_boundary_to_request_facade`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

Guard 现在证明：

- `TurnoverLedgerApiRoutes` 拥有 closure confirm route-owner 方法；
- `server.py` 不再定义 `_handle_api_turnover_ledger_closure_confirm(...)`；
- closure withdraw 和 relation withdraw callbacks 仍保留在 `server.py`；
- `server.py` 注入 closure request-boundary port。

计划验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_closure_confirm_handler_delegates_affected_months_boundary_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_and_withdraw_require_mutation_permission_and_write_audit -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

## 七类测试适用性

1. Business core unit tests：不适用；未改 manual zero-difference closure 的金额、分组、row type 或状态规则。
2. Service-layer tests：适用但未新增；closure request boundary/write facade/UoW 既有回归继续覆盖 Workbench relation command service wiring、affected-months、stale precondition、idempotency 和 refresh side effects。
3. API contract tests：适用；复跑 closure confirm targeted regressions 和完整 `tests.test_turnover_ledger_api`，覆盖 permission、response shape 和 closure/withdraw wiring。
4. Read model/cache/background job tests：间接受影响；closure confirm 成功后的 `turnover_ledger:all` refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
5. Frontend component and interaction tests：不适用；未改前端 API mapper、manual closure UI 或 operation overlay。
6. End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移 HTTP mapping，不改变 closure business flow。
7. Existing feature regression tests：适用；更新 platform Guard 防止 closure confirm callback 回到 `server.py`，并确认 withdraw callbacks 未被误删。

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- closure withdraw 和 relation withdraw callbacks 仍待迁移。

## 下一步

选择 `server-py:turnover-ledger-closure-withdraw-route-callback-collapse`，单独迁移 `POST /api/turnover-ledger/closures/withdraw`，保持 relation withdraw callback 不变。
