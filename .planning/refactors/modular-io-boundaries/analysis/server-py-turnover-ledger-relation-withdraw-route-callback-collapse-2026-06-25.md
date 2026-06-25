# server-py:turnover-ledger-relation-withdraw-route-callback-collapse

日期：2026-06-25

## 结论

`POST /api/turnover-ledger/relations/{relation_id}/withdraw` 的 HTTP mapping 已从 `server.py` 迁入 `TurnoverLedgerApiRoutes.route(...)`。

`server.py` 不再定义：

- `_handle_api_turnover_ledger_withdraw(...)`

至此，当前已知 `/api/turnover-ledger*` route callbacks 已全部迁入 `TurnoverLedgerApiRoutes` 或其他显式边界；后续需要单独做 local closure audit 证明 `server.py` 只保留组合根、平台 adapter 和 provider/helper ports。

## 实现

`TurnoverLedgerApiRoutes.route(...)` 新增 `POST /api/turnover-ledger/relations/{relation_id}/withdraw` 分支，解析 URL 中的 `relation_id` 后调用：

- `handle_withdraw_relation_route(...)`

新增显式端口：

- `withdraw_request_boundary_provider`

该端口由 `Application` 在组合根注入：

- `withdraw_request_boundary_provider=self._turnover_ledger_withdraw_request_boundary_facade`

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
- relation id 仍由 URL path 解码得到；
- actor fallback 仍为 `username -> user_id -> web_finance_user`；
- tenant 仍由 `tenant_id_for_session(...)` port 提供；
- `idempotency_key` / `idempotencyKey` 兼容保留；
- withdraw request boundary 继续负责 relation detail precheck、expected_versions、affected-months、stale precondition、write facade、idempotency 和 refresh side effects；
- `KeyError` 继续返回 404 `unknown_relation_id`；
- `TurnoverLedgerWithdrawRequestBoundaryError` 继续按自带 `status_code` 和 `error_code` 映射；
- `TurnoverLedgerWritePreconditionError` 继续通过 `write_precondition_error_payload` 生成 response payload；
- `WorkbenchIdempotency*` 继续映射 409；
- `TurnoverRelationValidationError` 继续映射 400 并保留 `error_code`；
- 成功 response shape 不变。

## 测试和 Guard

更新：

- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_withdraw_relation_handler_does_not_inline_legacy_fallback_side_effects`
- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_withdraw_handler_delegates_precheck_expected_versions_and_affected_months_to_request_facade`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

Guard 现在证明：

- `TurnoverLedgerApiRoutes` 拥有 relation withdraw route-owner 方法；
- `server.py` 不再定义 `_handle_api_turnover_ledger_withdraw(...)`；
- `server.py` 注入 withdraw request-boundary port；
- `server.py` 不再保留 turnover ledger route callback retained-list。

计划验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_relation_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_handler_delegates_precheck_expected_versions_and_affected_months_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_request_boundary_facade_wires_relation_detail_and_affected_months_resolver tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_idempotency_key_replays_without_duplicate_withdraw_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_relation_queue_failure_rolls_back_relation_withdraw tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_relation_uow_path_does_not_clear_read_model_directly -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

## 七类测试适用性

1. Business core unit tests：不适用；未改 relation withdraw 的业务规则。
2. Service-layer tests：适用但未新增；withdraw request boundary/write facade/UoW 既有回归继续覆盖 relation detail precheck、expected_versions、affected-months、stale precondition、idempotency 和 refresh side effects。
3. API contract tests：适用；复跑 withdraw targeted regressions 和完整 `tests.test_turnover_ledger_api`，覆盖 idempotency replay/conflict、queue failure rollback、UoW no-direct-clear、unknown relation/error mapping 和 response shape。
4. Read model/cache/background job tests：间接受影响；withdraw 成功后的 refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
5. Frontend component and interaction tests：不适用；未改前端 API mapper、toolbar withdraw UI 或 operation overlay。
6. End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移 HTTP mapping，不改变 relation withdraw business flow。
7. Existing feature regression tests：适用；更新 platform Guard 防止 relation withdraw callback 回到 `server.py`，并确认 turnover ledger route callbacks 已全部迁出。

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- 需要下一轮 local closure audit 证明剩余 turnover ledger `Application` surfaces 均为组合根/provider/platform/helper ports，而非 route ownership。

## 下一步

选择 `server-py:turnover-ledger-route-owner-local-closure-audit`，确认 `server.py` 不再拥有 `/api/turnover-ledger*` route callbacks，并分类剩余 turnover ledger app surfaces。
