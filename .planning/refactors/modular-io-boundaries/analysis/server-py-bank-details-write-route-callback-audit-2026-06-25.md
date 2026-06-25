# server-py:bank-details-write-route-callback-audit

日期：2026-06-25

## 结论

`server-py:bank-details-write-route-callback-audit` 已完成为 `analysis-closed`。

银行明细 read/export route-owner 已闭合后，`server.py` 仍保留 7 个 write callbacks：

- `_handle_api_bank_details_auto_tag_rules_update`
- `_handle_api_bank_details_auto_tag_rules_reapply`
- `_handle_api_bank_details_auto_tag_rules_file_replacement`
- `_handle_api_bank_detail_category_confirmation`
- `_handle_api_bank_detail_category_confirmation_delete`
- `_handle_api_bank_detail_category_assignment`
- `_handle_api_bank_detail_category_assignment_delete`

这些 callbacks 都已经委托 `BankDetailsApiRoutes` 的业务方法，没有直接写 app settings、category service、dirty/outbox 或 lifecycle；但它们仍在 `server.py` 持有 HTTP session/body/default-source/json mapping。

## 分组

### Auto-tag write group

候选下一实现：

`server-py:bank-details-auto-tag-write-route-callback-collapse`

范围：

- `PUT /api/bank-details/auto-tag-rules`
- `POST /api/bank-details/auto-tag-rules/reapply`
- `POST /api/bank-details/auto-tag-rules/file-replacement`

需要 route-owner ports：

- write/read session resolver：当前复用 `_resolve_bank_details_read_session(...)`；
- JSON body loader：`_load_json_body(...)`；
- JSON response：`_json_response(...)`；
- default bundled rules source provider：当前 `Application._default_bank_auto_tag_rules_file_source()`；
- 保留现有权限错误和 invalid body 响应。

风险：

- file replacement 空 body 时必须继续使用 bundled normalized rules；
- reapply 不读取 body，不能被 route body parser 拦截；
- PUT 成功后的 lifecycle、dirty/outbox、audit 仍由 `BankDetailsApplicationService` / `AppSettingsService` 负责，route owner 不能内联。

### Category write group

后续实现候选：

`server-py:bank-details-category-write-route-callback-collapse`

范围：

- `POST/DELETE /api/bank-details/transactions/{transaction_id}/category-confirmation`
- `POST/DELETE /api/bank-details/transactions/{transaction_id}/category-assignment`

风险：

- transaction id route extraction、permission denial、JSON body parsing、version/conflict errors 和 category side-effect port 需要单独保护；
- 该组涉及人工补分类和候选确认，建议等 auto-tag write group 收口后再迁移。

## 下一步

选择 `server-py:bank-details-auto-tag-write-route-callback-collapse` 作为下一条实现边界。

本审计不改运行时代码，不执行生产验证，不声明 bank-details module/global closure。

## 验证命令

```bash
bash scripts/verify.sh docs
git diff --check
```

## 未测风险

- 未运行生产 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin 或生产写入验证。
- 未迁移 category confirmation/assignment callbacks。
- 本审计不改变测试覆盖；下一实现 slice 必须增加 API/Guard 回归。
