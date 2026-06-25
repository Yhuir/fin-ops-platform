# planning:post-turnover-ledger-route-owner-next-boundary-selection

日期：2026-06-25

## 结论

T0 在 turnover ledger route-owner 本地闭环后，选择下一条本地实现边界：

`server-py:bank-details-read-export-route-callback-collapse`

该边界只迁移银行明细 read/export HTTP mapping，不处理自动标签规则写入、分类确认/人工补分类写入、生产验证或 Go hot-path。

## 选择依据

`server.py` 仍保留多组 app-owned route callbacks。当前最高收益且可安全拆小的是 `bank-details`：

- `routes_bank_details.py` 已存在 `BankDetailsApiRoutes`，业务方法已经在 route owner 内；
- `server.py` 仍持有 `/api/bank-details/accounts`、`/transactions`、`/transactions/export`、`/auto-tag-rules` 的 HTTP 分发、query/session/json/export response wrapper；
- 银行明细是多个下游模块的事实源，但本 slice 只迁移 HTTP mapping，不改 canonical facts、dirty scopes、outbox、read model refresh、cache 或业务规则；
- 自动标签写入和分类写入权限/body/side-effect 风险更高，应作为后续写入 slice 单独审计和迁移。

## 残余 surface 证据

静态扫描显示 `server.py` 仍定义银行明细 callbacks：

```bash
rg -n "^    def _handle_api_bank" backend/src/fin_ops_platform/app/server.py
```

候选 read/export callbacks：

- `_handle_api_bank_details_accounts`
- `_handle_api_bank_details_auto_tag_rules`
- `_handle_api_bank_details_transactions`
- `_handle_api_bank_details_transactions_export`

暂不纳入本 slice 的 write callbacks：

- `_handle_api_bank_details_auto_tag_rules_update`
- `_handle_api_bank_details_auto_tag_rules_reapply`
- `_handle_api_bank_details_auto_tag_rules_file_replacement`
- `_handle_api_bank_detail_category_confirmation`
- `_handle_api_bank_detail_category_confirmation_delete`
- `_handle_api_bank_detail_category_assignment`
- `_handle_api_bank_detail_category_assignment_delete`

## 下一实现边界

`server-py:bank-details-read-export-route-callback-collapse`

预期实现：

- 在 `BankDetailsApiRoutes` 增加 `route(...)` 或等价 route-owner HTTP mapping；
- 注入显式平台 ports，例如 `json_response`、`resolve_read_session`、`export_response`；
- 将 `/api/bank-details/accounts`、`/transactions`、`/transactions/export`、`/auto-tag-rules` 从 `server.py` dispatch 移到 `routes_bank_details.py`；
- 删除对应 app-owned callbacks；
- 增加/更新 API route tests 和 platform Guard，证明 read/export callbacks 不回流；
- 保留自动标签写入和分类写入 callbacks 作为后续边界。

## Docs Impact

- 需要更新本分析文件、queue/state/journal/next prompt 和主控 prompt。
- 实现 slice 完成后需要更新 `docs/modules/bank-details/implementation-notes.md` 与 `docs/modules/bank-details/tests.md`。
- 本 selection slice 不改变长期产品/API/read model/worker 事实源。

## 验证命令

```bash
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 本轮仅选择边界，不改运行时代码。
- 未执行真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin 或生产写入验证。
- 银行明细写入 callbacks 和 route-owner local closure 仍待后续 slice。
