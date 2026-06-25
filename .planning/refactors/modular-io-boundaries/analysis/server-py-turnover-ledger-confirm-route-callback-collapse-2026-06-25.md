# server-py:turnover-ledger-confirm-route-callback-collapse

日期：2026-06-25

## 结论

`POST /api/turnover-ledger/relations/confirm` 的 HTTP mapping 已从 `server.py` 迁入 `TurnoverLedgerApiRoutes.route(...)`。

`server.py` 不再定义：

- `_handle_api_turnover_ledger_confirm(...)`

其他 turnover ledger mutation callbacks 保持不变：

- `_handle_api_turnover_ledger_closure_confirm(...)`
- `_handle_api_turnover_ledger_closure_withdraw(...)`
- `_handle_api_turnover_ledger_withdraw(...)`

## 实现

`TurnoverLedgerApiRoutes.route(...)` 新增 `POST /api/turnover-ledger/relations/confirm` 分支，调用：

- `handle_confirm_relation_route(...)`

新增显式端口：

- `confirm_relation_request_boundary_provider`

该端口由 `Application` 在组合根注入：

- `confirm_relation_request_boundary_provider=self._turnover_ledger_confirm_request_boundary_facade`

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
- confirm request boundary 继续负责 affected-months、stale precondition、write facade、idempotency 和 refresh side effects；
- `TurnoverRelationValidationError` 继续映射 400 并保留 `error_code`；
- `TurnoverLedgerWritePreconditionError` 继续通过 `write_precondition_error_payload` 生成 response payload；
- `WorkbenchIdempotency*` 继续映射 409；
- 成功 response shape 不变。

## 测试和 Guard

更新：

- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_confirm_relation_handler_does_not_inline_legacy_fallback_side_effects`
- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_confirm_handler_delegates_affected_months_boundary_to_request_facade`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

Guard 现在证明：

- `TurnoverLedgerApiRoutes` 拥有 confirm route-owner 方法；
- `server.py` 不再定义 `_handle_api_turnover_ledger_confirm(...)`；
- closure confirm、closure withdraw、relation withdraw callbacks 仍保留在 `server.py`；
- `server.py` 注入 confirm request-boundary port。

计划验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_relation_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_handler_delegates_affected_months_boundary_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_request_boundary_facade_owns_affected_months_resolution_and_response_field tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_request_expected_versions_reach_write_command tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_idempotency_key_replays_without_duplicate_confirm_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_relation_queue_failure_rolls_back_relation_confirm tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_relation_uow_path_does_not_clear_read_model_directly -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

## 七类测试适用性

1. Business core unit tests：不适用；未改确认关系的金额、分组、标签或状态规则。
2. Service-layer tests：适用但未新增；confirm request boundary/write facade/UoW 既有回归继续覆盖 affected-months、stale precondition、idempotency、rollback 和 refresh side effects。
3. API contract tests：适用；复跑 confirm targeted regressions 和完整 `tests.test_turnover_ledger_api`，覆盖 expected_versions、idempotency replay/conflict、queue failure rollback、UoW no-direct-clear 和 response shape。
4. Read model/cache/background job tests：间接受影响；confirm 成功后的 `turnover_ledger:all` refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
5. Frontend component and interaction tests：不适用；未改前端 API mapper、manual closure UI 或 operation overlay。
6. End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移旧 relation confirm callback，不改 closure confirm/withdraw 业务流。
7. Existing feature regression tests：适用；更新 platform Guard 防止 confirm callback 回到 `server.py`，并确认 closure/withdraw callbacks 未被误删。

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- closure confirm、closure withdraw 和 relation withdraw callbacks 仍待迁移。

## 下一步

选择 `server-py:turnover-ledger-closure-confirm-route-callback-collapse`，单独迁移 `POST /api/turnover-ledger/closures/confirm`，保持 closure withdraw 和 relation withdraw callbacks 不变。
