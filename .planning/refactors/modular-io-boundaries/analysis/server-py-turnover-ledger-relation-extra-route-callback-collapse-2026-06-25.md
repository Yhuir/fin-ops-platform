# server-py:turnover-ledger-relation-extra-route-callback-collapse

日期：2026-06-25

## 结论

`PUT /api/turnover-ledger/relations/{relation_id}/extra` 的 HTTP mapping 已从 `server.py` 迁入 `TurnoverLedgerApiRoutes.route(...)`。

`server.py` 不再定义：

- `_handle_api_turnover_ledger_relation_extra_update(...)`

其他 turnover ledger mutation callbacks 保持不变：

- `_handle_api_turnover_ledger_confirm(...)`
- `_handle_api_turnover_ledger_closure_confirm(...)`
- `_handle_api_turnover_ledger_closure_withdraw(...)`
- `_handle_api_turnover_ledger_withdraw(...)`

## 实现

`TurnoverLedgerApiRoutes.route(...)` 新增 `PUT /api/turnover-ledger/relations/{relation_id}/extra` 分支，调用：

- `handle_relation_extra_update_route(...)`

新增显式端口：

- `relation_extra_request_boundary_provider`
- `relation_extra_tenant_id_provider`
- `write_precondition_error_payload`

这些端口由 `Application` 在组合根注入：

- `relation_extra_request_boundary_provider=self._turnover_ledger_relation_extra_request_boundary_facade`
- `relation_extra_tenant_id_provider=self._workbench_reconciliation_tenant_id`
- `write_precondition_error_payload=self._turnover_write_precondition_error_payload`

Route owner 复用 Row381 已注入的 mutation ports：

- `mutation_session_resolver`
- `session_error_detector`
- `load_json_body`

Route owner 仍不 import `app.auth`，不读取 cookie/header 细节，不接收 whole `Application`。

## 行为保持

保持原 HTTP 行为：

- mutation permission 失败仍返回原 session resolver response；
- invalid JSON/body 仍返回 `_load_json_body(...)` 的错误 response；
- payload 非 object -> 400 `invalid_turnover_ledger_extra`；
- actor fallback 仍为 `username -> user_id -> web_finance_user`；
- tenant 仍由 `_workbench_reconciliation_tenant_id()` port 提供；
- relation extra request boundary 继续负责 `expected_versions`、`idempotency_key`、stale precondition、normalization、write facade 和 refresh side effects；
- unknown relation 继续返回 404 `unknown_relation_id`；
- `TurnoverLedgerRelationExtraRequestBoundaryError` 继续按自带 `status_code` 和 `error_code` 映射；
- `TurnoverLedgerWritePreconditionError` 继续通过 `write_precondition_error_payload` 生成 response payload；
- `WorkbenchIdempotency*` 继续映射 409；
- `TurnoverLedgerExtraValidationError` 和 `ValueError` 继续映射 400 `invalid_turnover_ledger_extra`；
- 成功 response shape 不变。

## 测试和 Guard

更新：

- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_relation_extra_handler_does_not_inline_legacy_fallback_side_effects`
- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_relation_extra_handler_delegates_expected_versions_idempotency_and_stale_boundary`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

Guard 现在证明：

- `TurnoverLedgerApiRoutes` 拥有 relation-extra PUT route-owner 方法；
- `server.py` 不再定义 `_handle_api_turnover_ledger_relation_extra_update(...)`；
- confirm/closure/withdraw callbacks 仍保留在 `server.py`；
- `server.py` 注入 relation-extra request-boundary、tenant 和 stale-precondition payload ports。

计划验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_handler_delegates_expected_versions_idempotency_and_stale_boundary tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_get_returns_default_structure_and_put_persists tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_put_rejects_invalid_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_put_rejects_readonly_user tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_relation_extra_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_relation_extra_idempotency_key_replays_without_duplicate_save_or_refresh -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

## 七类测试适用性

1. Business core unit tests：不适用；未改 extra 字段业务校验、金额、标签、闭环或撤回规则。
2. Service-layer tests：适用但未新增；relation extra request boundary/write facade 既有回归继续覆盖 normalization、stale precondition、idempotency、extra save 和 refresh side effects。
3. API contract tests：适用；复跑 relation-extra targeted regressions 和完整 `tests.test_turnover_ledger_api`，覆盖 GET default、PUT persist、invalid payload、readonly、idempotency replay/conflict 和 response shape。
4. Read model/cache/background job tests：间接受影响；relation extra 成功后的 `turnover_ledger:all` refresh 由既有 API tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
5. Frontend component and interaction tests：不适用；未改前端 API mapper、extra drawer、operation overlay 或页面交互。
6. End-to-end business-flow integration tests：不适用；未改 manual closure confirm/withdraw 业务流。
7. Existing feature regression tests：适用；更新 platform Guard 防止 relation-extra callback 回到 `server.py`，并确认 confirm/closure/withdraw callbacks 未被误删。

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- confirm、closure 和 withdraw callbacks 仍待迁移。

## 下一步

选择 `server-py:turnover-ledger-confirm-route-callback-collapse`，单独迁移 `POST /api/turnover-ledger/relations/confirm`，保持 closure confirm/withdraw 和 relation withdraw callbacks 不变。
