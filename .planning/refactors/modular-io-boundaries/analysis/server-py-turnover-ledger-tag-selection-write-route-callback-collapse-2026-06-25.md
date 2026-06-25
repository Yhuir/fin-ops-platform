# server-py:turnover-ledger-tag-selection-write-route-callback-collapse

日期：2026-06-25

## 结论

`PUT /api/turnover-ledger/tag-selection` 的 HTTP mapping 已从 `server.py` 迁入 `TurnoverLedgerApiRoutes.route(...)`。

`server.py` 不再定义：

- `_handle_api_turnover_ledger_tag_selection_update(...)`

其他 turnover ledger mutation callbacks 保持不变：

- `_handle_api_turnover_ledger_bank_row_tags_batch(...)`
- `_handle_api_turnover_ledger_relation_extra_update(...)`
- `_handle_api_turnover_ledger_confirm(...)`
- `_handle_api_turnover_ledger_closure_confirm(...)`
- `_handle_api_turnover_ledger_closure_withdraw(...)`
- `_handle_api_turnover_ledger_withdraw(...)`

## 实现

`TurnoverLedgerApiRoutes.route(...)` 新增 `PUT /api/turnover-ledger/tag-selection` 分支，调用：

- `handle_tag_selection_update_route(...)`

新增显式端口：

- `mutation_session_resolver`
- `session_error_detector`
- `load_json_body`
- `tenant_id_provider`
- `tag_selection_write_boundary_provider`

这些端口由 `Application` 在组合根注入：

- `mutation_session_resolver=self._turnover_mutation_session`
- `session_error_detector=lambda value: isinstance(value, Response)`
- `load_json_body=self._load_json_body`
- `tenant_id_provider=tenant_id_for_session`
- `tag_selection_write_boundary_provider=self._turnover_ledger_tag_selection_request_boundary_facade`

Route owner 仍不 import `app.auth`，不读取 cookie/header 细节，不接收 whole `Application`。

## 行为保持

保持原 HTTP 行为：

- mutation permission 失败仍返回原 session resolver response；
- invalid JSON/body 仍返回 `_load_json_body(...)` 的错误 response；
- actor fallback 仍为 `username -> user_id -> web_finance_user`；
- tenant 仍由 `tenant_id_for_session(...)` port 提供；
- `idempotency_key` / `idempotencyKey` 兼容保留；
- `AppSettingsValidationError` 继续映射：
  - `turnover_ledger_tag_selection_version_conflict` -> 409；
  - 其他 settings validation -> 400；
- `WorkbenchIdempotencyKeyConflict`、`WorkbenchIdempotencyInProgress`、`WorkbenchIdempotencyFailed` 继续映射 409；
- 成功 response shape 不变。

## 测试和 Guard

更新：

- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_turnover_ledger_tag_selection_handler_does_not_inline_legacy_fallback_side_effects`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

Guard 现在证明：

- `TurnoverLedgerApiRoutes` 拥有 tag-selection PUT route-owner 方法；
- `server.py` 不再定义 `_handle_api_turnover_ledger_tag_selection_update(...)`；
- 其他 turnover ledger mutation callbacks 仍保留在 `server.py`；
- `server.py` 注入 tag-selection write route ports。

已运行验证：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_get_put_and_version_conflict tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_tag_selection_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_tag_selection_idempotency_key_replays_without_duplicate_settings_save_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

结果：

- targeted route-owner Guard: 1 test passed。
- targeted tag-selection API regressions: 5 tests passed。
- full `tests.test_turnover_ledger_api`: 140 tests passed。

## 七类测试适用性

1. Business core unit tests：不适用；未改外部往来标签准入业务规则，只迁移 HTTP mapping。
2. Service-layer tests：适用但未新增；tag-selection request boundary/write facade 既有回归继续覆盖 settings persistence、idempotency 和 refresh rollback。
3. API contract tests：适用；复跑 tag-selection API tests 和完整 `tests.test_turnover_ledger_api`。
4. Read model/cache/background job tests：间接受影响；tag-selection 成功后的 `turnover_ledger:all` refresh/rollback 由既有 API tests 覆盖，本 slice 未改 worker。
5. Frontend component and interaction tests：不适用；未改前端 mapper 或页面交互。
6. End-to-end business-flow integration tests：不适用；未改 confirm/withdraw/closure flow。
7. Existing feature regression tests：适用；更新 platform Guard 防止 tag-selection callback 回到 `server.py`，并确认其他写 callbacks 未被误删。

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- bank-row-tags、relation-extra、confirm、closure 和 withdraw callbacks 仍待迁移。

## 下一步

选择 `server-py:turnover-ledger-bank-row-tags-route-callback-collapse`，单独迁移 `POST /api/turnover-ledger/bank-row-tags/batch`，保持 target validator、affected-months resolver 和 legacy fallback ports 明确注入。
