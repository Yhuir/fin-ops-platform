# server-py:turnover-ledger-bank-row-tags-route-callback-collapse

日期：2026-06-25

## 结论

`POST /api/turnover-ledger/bank-row-tags/batch` 的 HTTP mapping 已从 `server.py` 迁入 `TurnoverLedgerApiRoutes.route(...)`。

`server.py` 不再定义：

- `_handle_api_turnover_ledger_bank_row_tags_batch(...)`

其他 turnover ledger mutation callbacks 保持不变：

- `_handle_api_turnover_ledger_relation_extra_update(...)`
- `_handle_api_turnover_ledger_confirm(...)`
- `_handle_api_turnover_ledger_closure_confirm(...)`
- `_handle_api_turnover_ledger_closure_withdraw(...)`
- `_handle_api_turnover_ledger_withdraw(...)`

## 实现

`TurnoverLedgerApiRoutes.route(...)` 新增 `POST /api/turnover-ledger/bank-row-tags/batch` 分支，调用：

- `handle_bank_row_tags_batch_route(...)`

新增显式端口：

- `bank_row_tags_request_boundary_provider`

该端口由 `Application` 在组合根注入：

- `bank_row_tags_request_boundary_provider=self._turnover_ledger_bank_row_tags_request_boundary_facade`

Route owner 复用 Row381 已注入的 mutation ports：

- `mutation_session_resolver`
- `session_error_detector`
- `load_json_body`
- `tenant_id_provider`

Route owner 仍不 import `app.auth`，不读取 cookie/header 细节，不接收 whole `Application`。

## 行为保持

保持原 HTTP 行为：

- mutation permission 失败仍返回原 session resolver response；
- invalid JSON/body 仍返回 `_load_json_body(...)` 的错误 response；
- `updates` 缺失或非 array -> 400 `invalid_turnover_bank_row_tag_update`；
- `updates` 中元素非 object -> 400 `invalid_turnover_bank_row_tag_update`；
- actor fallback 仍为 `username -> user_id -> web_finance_user`；
- tenant 仍由 `tenant_id_for_session(...)` port 提供；
- `idempotency_key` / `idempotencyKey` 兼容保留；
- target validation、affected-months resolution、legacy fallback 仍由 `TurnoverLedgerBankRowTagsRequestBoundaryFacade` 以及 app 注入的 validator/resolver ports 负责；
- `WorkbenchIdempotency*` 继续映射 409；
- `BankTransactionCategoryConflictError` 继续映射 409 并保留 `transaction_id`、`expected_version`、`actual_version`；
- `BankTransactionCategoryValidationError` 继续映射 400 并保留 `transaction_id`；
- 成功 response shape 不变。

## 测试和 Guard

更新：

- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_target_turnover_bank_row_tag_batch_handler_does_not_inline_legacy_fallback_side_effects`
- `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_bank_row_tags_handler_delegates_validation_affected_months_and_flags_to_request_facade`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`

Guard 现在证明：

- `TurnoverLedgerApiRoutes` 拥有 bank-row-tags batch route-owner 方法；
- `server.py` 不再定义 `_handle_api_turnover_ledger_bank_row_tags_batch(...)`；
- relation-extra/confirm/closure/withdraw callbacks 仍保留在 `server.py`；
- `server.py` 注入 bank-row-tags request-boundary port。

已运行验证：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_turnover_bank_row_tag_batch_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_handler_delegates_validation_affected_months_and_flags_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tag_batch_save_updates_category_and_reflects_to_bank_details tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tag_batch_rejects_non_turnover_rows_without_refresh_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_bank_row_tags_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_bank_row_tags_idempotency_key_replays_without_duplicate_category_update_relation_rebuild_or_refresh -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

结果：

- targeted route-owner Guard: 1 test passed。
- targeted bank-row-tags API regressions: 6 tests passed。
- full `tests.test_turnover_ledger_api`: 140 tests passed。

## 七类测试适用性

1. Business core unit tests：不适用；未改外部往来标签规则或分类业务规则，只迁移 HTTP mapping。
2. Service-layer tests：适用但未新增；bank-row-tags request boundary/write facade 既有回归继续覆盖 target validation、affected months、idempotency、legacy fallback 和 refresh side effects。
3. API contract tests：适用；复跑 bank-row-tags targeted regressions 和完整 `tests.test_turnover_ledger_api`。
4. Read model/cache/background job tests：间接受影响；bank-row-tags 成功后的 bank detail/workbench/turnover refresh 由既有 API tests 覆盖，本 slice 未改 worker。
5. Frontend component and interaction tests：不适用；未改前端 API mapper、页面交互或 operation overlay。
6. End-to-end business-flow integration tests：不适用；未改 confirm/withdraw/closure flow。
7. Existing feature regression tests：适用；更新 platform Guard 防止 bank-row-tags callback 回到 `server.py`，并确认其他写 callbacks 未被误删。

## 未测风险

- 未执行真实 PostgreSQL、RabbitMQ、Redis、systemd worker、Browser、admin 或生产写入验证。
- relation-extra、confirm、closure 和 withdraw callbacks 仍待迁移。

## 下一步

选择 `server-py:turnover-ledger-relation-extra-route-callback-collapse`，单独迁移 `PUT /api/turnover-ledger/relations/{relation_id}/extra`，保持 stale precondition、idempotency 和 relation extra request-boundary behavior。
