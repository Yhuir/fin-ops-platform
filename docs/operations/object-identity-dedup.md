# 对象身份与去重规则审计

本文档描述业务对象 identity/dedup 的生产审计方式。当前闭环统一规则入口，并以 canonical app facts 与 relation facts 为准；不启用独立的 `object_identity` 分发 read model。

## 规则边界

- 统一入口是 `FinancialObjectIdentityPolicy`、`ObjectDedupDecisionService` 和 repository 查询边界。
- 发票、银行流水、OA 附件票、ETC 发票、税局认证记录和导入预览行不得在页面 service、parser、server 或运维工具中私有拼 identity key。
- `InvoiceIdentityService` 和 `BankTransactionIdentityService` 是底层兼容策略，可以被 policy 复用。
- `source_unique_key`、`data_fingerprint` 和现有唯一索引继续保留。
- Workbench 展示状态由 `WorkbenchObjectIdentityArbitrationService` 在分组前仲裁：正式发票与 OA 附件发票命中同一强发票 identity 时，只允许进入一个最终展示区。
- 强发票 identity 只包含数电发票号、发票代码+号码。税额指纹、金额、项目、申请人、对方名称等弱字段只用于审计提示，不用于自动跨来源合并。
- 银行流水只有在稳定 business-fields identity 完整且其中一条已被 paired/异常/忽略占用时，才压制同 identity 的 open 别名；全 open 重复只审计。
- OA 单据以 `row_id` 为主身份，`form_id`/`workflow_no` 只作为 alias 审计线索，不按金额、申请人或项目推断合并。
- 历史冲突不做破坏性合并。审计输出报告，人工 repair 或 direct payload/relation diagnostics 恢复后再重新审计。

## 生产审计命令

在服务器发布完成、环境变量指向生产 PostgreSQL 后执行：

```bash
cd /path/to/fin-ops-platform
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.audit_object_identity --json --limit 50
```

报告覆盖：

- `app.invoices`：正式发票 canonical key、stored key mismatch、duplicate canonical、missing canonical；其中 blocking 只看数电发票号、发票代码+号码这两类强 identity，税额指纹只作为 warning。
- `app.bank_transactions`：银行流水 canonical key、stored key mismatch、duplicate canonical、missing canonical。
- `app.etc_invoices`：ETC 原始票 canonical key、duplicate canonical、missing canonical。该表是原始来源事实，重复只作为 warning；正式发票是否重复以 canonical `app.invoices` 为准。
- `app.invoices.etc_invoice_id`：已关联到统一发票池既有 canonical 发票的 ETC metadata 数量。
- `app.oa_attachment_invoice_cache`：OA 附件票缓存中的正式发票 evidence/invoices canonical、suspected duplicate、missing canonical。
- `app.oa_attachment_invoice_cache_sources` / `app.oa_attachments`：将 OA 附件票缓存 key 映射回真实附件和 OA，用于区分“缓存内部重复”和“跨 OA 重复发票”。
- `app.oa_applications`：同一 `form_id` 是否映射多个 `row_id`，用于排查 OA alias 风险。
- `app.workbench_pair_relations`：active relation 中是否存在指向已不存在对象的 row_id。

## 表状态

报告中的可选事实表会带 table status：

- `available`：表存在，count 为真实扫描结果。
- `missing`：表不存在或环境未部署对应 schema，count 固定为 0。

`missing` 不等同于业务数据为 0，也不会自动计入 blocking issue。出现 `missing` 时，先核对 migration/部署环境是否完整，再判断是否需要补库或跳过该业务域审计。

## 退出码

- `0`：没有 blocking issue。
- `1`：存在 blocking issue，需要人工处理后重跑。

Blocking issue 包含：

- 同一强发票 identity 下出现多条正式发票。强 identity 只包含数电发票号、发票代码+号码。
- 同一 canonical key 下出现多条银行流水。
- 同一 OA 附件票强 canonical key 出现在多个不同 OA 报销中。强 key 包含数电票号、发票代码+号码、附件稳定 hash；`seller_tax_no + buyer_tax_no + invoice_date + total_with_tax` 这类弱税额指纹不作为 OA 附件票 blocking key。
- 历史 `source_unique_key` 与当前强发票或银行 policy canonical key 不一致。正式发票弱税额指纹 mismatch 不阻断发布。
- Active workbench relation 指向已不存在的 row_id。
- Active workbench relation 的成员 row 在 active Workbench generation 中缺失、拆组、重复 visible owner、payload relation 不一致，或 `all` generation 旧于成员月份 generation。

非 blocking warning：

- missing canonical 示例。
- suspected duplicate group。
- 正式发票只命中弱税额指纹的 duplicate 或 key mismatch；必须人工核对票号、税号、日期和金额后再决定是否需要业务 repair。
- `app.etc_invoices` 原始来源表的 duplicate canonical group；该表重复不代表 canonical `app.invoices` 正式事实重复。
- OA 附件票同一实际附件、同一 OA 内多个附件或历史 cache key 产生的重复 evidence。
- OA 附件票只命中弱税额指纹的跨 OA 疑似重复；必须人工核对发票号码、乘车人、行程等票面信息。
- OA `form_id` 对应多个 `row_id` 的 alias group；需要结合 `PostgresOAProjectionRepository` 的 alias migration 和源系统事实处理。

这些只用于人工排查，不自动阻断发布，也不自动合并历史对象。

## Repair 原则

- 先确认业务事实，再处理数据；不要只因为 key 相同就合并。
- canonical duplicate 优先查原始导入批次、附件来源、ETC 批次和税局认证记录。
- 修复应通过已有业务命令、专用 repair 工具或 migration 脚本完成，并保留审计记录。
- 修复或发布后必须重读受影响 Workbench/workbench_relation direct payload，再重新执行审计命令，确认 `blocking_issue_count=0`。
- relation display 不一致的生产修复只能使用已有业务命令或专用 repair 工具重新触发 canonical relation facts；禁止手改 legacy read model 投影行。

## 后续扩展条件

本轮只在 Workbench direct payload 的事实查询侧暴露 identity 证据，不新增独立 object identity read model 或 worker。只有当两个以上页面需要展示 duplicate group、canonical object 或 source lineage，且 direct query 已有真实性能瓶颈证据时，才允许设计可删除短 TTL response cache 或专用查询索引；不得恢复页面 read-model freshness、worker、manifest 或 systemd env。
