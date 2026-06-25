# server-py:bank-details-route-owner-local-closure-audit

日期：2026-06-25

## 结论

`server-py:bank-details-route-owner-local-closure-audit` 已完成为 `analysis-closed`，但 bank-details route-owner 尚未本地闭合。

审计确认已迁移的 callbacks 不再存在：

- `_handle_api_bank_details_accounts`
- `_handle_api_bank_details_auto_tag_rules`
- `_handle_api_bank_details_transactions`
- `_handle_api_bank_details_transactions_export`
- `_handle_api_bank_details_auto_tag_rules_update`
- `_handle_api_bank_details_auto_tag_rules_reapply`
- `_handle_api_bank_details_auto_tag_rules_file_replacement`
- `_handle_api_bank_detail_category_confirmation`
- `_handle_api_bank_detail_category_confirmation_delete`
- `_handle_api_bank_detail_category_assignment`
- `_handle_api_bank_detail_category_assignment_delete`

但 `server.py` 仍保留一个 bank-details path callback：

- `PATCH /api/bank-details/transactions/categories`
- `_handle_api_bank_transaction_categories(...)`

因此不能声明 bank-details route-owner local closure。

## 证据

静态搜索：

```bash
rg -n "def _handle_api_bank_details|def _handle_api_bank_detail_category|_handle_api_bank_details|_handle_api_bank_detail_category" backend/src/fin_ops_platform/app/server.py
```

结果：无输出。

Route path evidence：

```bash
rg -n "route_path.*bank-details|/api/bank-details" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_bank_details.py
```

结论：

- `routes_bank_details.py` 已拥有 auto-tag、accounts、transactions、export、category confirmation/assignment route branches；
- `server.py` 仍命中 delegating dispatch；
- `server.py` 仍有 `PATCH /api/bank-details/transactions/categories` app-owned branch。

## 下一步

选择下一实现边界：

`server-py:bank-details-transaction-categories-route-callback-collapse`

范围：

- 将 `PATCH /api/bank-details/transactions/categories` HTTP mapping 移入 `BankDetailsApiRoutes.route(...)` 或另一个明确 route owner；
- 注入或复用 session/json-body/json-response ports；
- 删除 `_handle_api_bank_transaction_categories(...)`；
- 保留其现有禁用/错误语义，避免恢复旧 bulk category mutation。

## 未测风险

- 本 audit 不改运行时代码。
- 未执行生产 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin 或生产写入验证。
- bank-details route-owner closure 仍待 PATCH categories 路径迁移后再次审计。
