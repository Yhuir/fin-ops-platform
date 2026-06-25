# server-py:turnover-ledger-write-route-callback-audit

日期：2026-06-25

## 结论

`server.py` 仍拥有 7 个 `/api/turnover-ledger*` 写路径 callbacks。本轮仅做审计，不迁移运行时代码。

最小下一实现边界选择：

`server-py:turnover-ledger-tag-selection-write-route-callback-collapse`

原因：tag-selection PUT 是当前剩余写路径中最薄的 HTTP wrapper，只负责 mutation session、JSON body、actor/tenant/idempotency 提取、`TurnoverLedgerTagSelectionRequestBoundaryFacade` 调用以及 settings/idempotency 错误映射。它不直接做 bank row 目标校验、stale precondition、Workbench relation command、affected-months 推导或 legacy side effects。

## 当前剩余 callbacks

### 1. tag-selection PUT

Callback：

- `_handle_api_turnover_ledger_tag_selection_update(...)`

职责：

- `_turnover_mutation_session(headers)`；
- `_load_json_body(body)`；
- actor fallback；
- `idempotency_key` 提取；
- `TurnoverLedgerTagSelectionRequestBoundaryFacade.update_tag_selection_from_request(...)`；
- `AppSettingsValidationError` 到 400/409；
- `WorkbenchIdempotency*` 到 409；
- 200 JSON response。

已存在边界：

- `_turnover_ledger_tag_selection_request_boundary_facade(...)`
- `TurnoverLedgerTagSelectionRequestBoundaryFacade`
- `_turnover_ledger_tag_selection_write_facade(...)`

判断：可直接迁入 `TurnoverLedgerApiRoutes.route(...)` 的 PUT 分支，前提是 route owner 只接收显式 ports，不直接 import `app.auth` 或读取 cookie。需要注入 mutation session resolver、JSON loader、tenant resolver、tag-selection request-boundary provider 和 settings/idempotency error mapper 或 response mapper。

### 2. bank-row-tags batch POST

Callback：

- `_handle_api_turnover_ledger_bank_row_tags_batch(...)`

职责：

- mutation session；
- JSON body；
- `updates` shape 校验；
- actor/idempotency 提取；
- `TurnoverLedgerBankRowTagsRequestBoundaryFacade.update_bank_row_tags_batch_from_request(...)`；
- idempotency/conflict/validation 错误映射。

已存在边界：

- `_turnover_ledger_bank_row_tags_request_boundary_facade(...)`
- `TurnoverLedgerBankRowTagsRequestBoundaryFacade`
- `_ensure_turnover_bank_row_tag_targets(...)`
- `_bank_transaction_category_affected_months(...)`

判断：比 tag-selection 稍厚，因为 request boundary 仍通过 app-injected target validator 和 affected-months resolver 进入 bank detail/read-model/tag reader 口径。可以后续迁入 route owner，但应单独做 `bank-row-tags` slice，避免和 tag-selection 混在一个提交里。

### 3. relation extra PUT

Callback：

- `_handle_api_turnover_ledger_relation_extra_update(...)`

职责：

- mutation session；
- JSON body；
- payload object 校验；
- actor；
- `TurnoverLedgerRelationExtraRequestBoundaryFacade.update_relation_extra_from_request(...)`；
- KeyError、request-boundary、write-precondition、idempotency、validation 错误映射。

已存在边界：

- `_turnover_ledger_relation_extra_request_boundary_facade(...)`
- `TurnoverLedgerRelationExtraRequestBoundaryFacade`
- `_turnover_write_precondition_error_payload(...)`

判断：可迁，但依赖 write-precondition payload mapping 与 relation extra stale contract，建议单独 slice。

### 4. relation confirm POST

Callback：

- `_handle_api_turnover_ledger_confirm(...)`

职责：

- mutation session；
- JSON body；
- `bank_row_ids` array 校验；
- actor/tenant/note/expected_versions/idempotency 提取；
- `TurnoverLedgerConfirmRequestBoundaryFacade.confirm_relation_from_request(...)`；
- validation/write-precondition/idempotency 错误映射。

判断：可迁，但与 closure confirm 共用 `TurnoverLedgerConfirmRequestBoundaryFacade` 和 affected-months/freshness 语义；应与 closure confirm 一起或在后续分组处理。

### 5. closure confirm POST

Callback：

- `_handle_api_turnover_ledger_closure_confirm(...)`

职责类似 relation confirm，但调用：

- `TurnoverLedgerConfirmRequestBoundaryFacade.confirm_zero_difference_closure_from_request(...)`

判断：涉及 manual zero-difference closure、Workbench relation command service 和 operation visibility targets，后续单独迁移更安全。

### 6. closure withdraw POST

Callback：

- `_handle_api_turnover_ledger_closure_withdraw(...)`

职责：

- mutation session；
- JSON body；
- `cash_closure_case_id`/note/idempotency；
- `TurnoverLedgerConfirmRequestBoundaryFacade.withdraw_cash_closure_case_from_request(...)`；
- validation/write-precondition/idempotency 错误映射。

判断：应与 closure confirm 或 withdraw group 分开迁移，不能与 tag-selection 混做。

### 7. relation withdraw POST

Callback：

- `_handle_api_turnover_ledger_withdraw(...)`

职责：

- mutation session；
- JSON body；
- actor/idempotency；
- `TurnoverLedgerWithdrawRequestBoundaryFacade.withdraw_relation_from_request(...)`；
- KeyError、request-boundary、write-precondition、idempotency、validation 错误映射。

判断：可迁，但撤回前置检查、relation version expected_versions 和 Workbench relation 恢复语义由 request boundary/facade 保护，建议单独处理。

## 现有测试保护

`tests/test_turnover_ledger_api.py` 已用 `inspect.getsource(...)` 保护写 callbacks 不得重新 inline legacy side effects：

- tag-selection 不得 inline settings update/clear/enqueue；
- bank-row-tags 不得 inline category save/rebuild/after-mutation；
- relation extra 不得 inline legacy persistence/refresh/stale checks；
- confirm/withdraw 不得 inline legacy relation mutation/affected-months/stale precheck。

Row379 新增的 `test_turnover_ledger_read_export_routes_use_route_owner` 也明确要求这些 mutation callbacks 当前仍存在，防止 read/export collapse 顺手迁移写路径。

## 下一实现建议

下一步只迁移：

- `PUT /api/turnover-ledger/tag-selection`

验收条件：

- `TurnoverLedgerApiRoutes.route(...)` 处理 tag-selection PUT；
- `server.py` 不再定义 `_handle_api_turnover_ledger_tag_selection_update(...)`；
- `server.py` 注入显式 route ports，不把 whole `Application` 传给 route owner；
- route owner 不 import `app.auth`，不直接读 cookie/header 细节，session 仍由 app-provided port 解析；
- 保持 status code、error code、response shape、idempotency 和 audit/refresh 行为不变；
- 更新现有 source-inspect tests 到 route-owner 方法；
- 更新 platform Guard：tag-selection write callback removed，其他 mutation callbacks retained。

## 验证

本轮为 analysis-only，无运行时代码变更。

已运行：

```bash
git status --short --branch
```

未运行测试，因为没有改代码。提交前仍需运行：

```bash
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 本轮不证明 mutation callbacks 已完成迁移。
- 未执行真实 PostgreSQL/worker/Browser/admin/write evidence。
- 下一实现 slice 必须复跑 `tests/test_turnover_ledger_api.py` 中 tag-selection 相关回归、route-owner Guard、py_compile、docs verify 和 diff check。
