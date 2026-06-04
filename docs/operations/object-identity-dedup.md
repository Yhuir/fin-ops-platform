# 对象身份与去重规则审计

本文档描述业务对象 identity/dedup 的生产审计方式。当前闭环只统一规则入口，不启用 `object_identity` 分发 read model。

## 规则边界

- 统一入口是 `FinancialObjectIdentityPolicy`、`ObjectDedupDecisionService` 和 repository 查询边界。
- 发票、银行流水、OA 附件票、ETC 发票、税局认证记录和导入预览行不得在页面 service、parser、server 或运维工具中私有拼 identity key。
- `InvoiceIdentityService` 和 `BankTransactionIdentityService` 是底层兼容策略，可以被 policy 复用。
- `source_unique_key`、`data_fingerprint` 和现有唯一索引继续保留；本轮不新增 migration。
- 历史冲突不自动合并。审计只输出报告，人工 repair 后再重新审计。

## 生产审计命令

在服务器发布完成、环境变量指向生产 PostgreSQL 后执行：

```bash
cd /path/to/fin-ops-platform
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.audit_object_identity --json --limit 50
```

报告覆盖：

- `app.invoices`：正式发票 canonical key、stored key mismatch、duplicate canonical、missing canonical。
- `app.bank_transactions`：银行流水 canonical key、stored key mismatch、duplicate canonical、missing canonical。
- `app.etc_invoices`：ETC 原始票 canonical key、duplicate canonical、missing canonical。
- `app.invoices.etc_invoice_id`：已同步到 canonical 发票的 ETC 数量。
- `app.oa_attachment_invoice_cache`：OA 附件票缓存中的正式发票 evidence/invoices canonical、suspected duplicate、missing canonical。
- `app.oa_attachment_invoice_cache_sources` / `app.oa_attachments`：将 OA 附件票缓存 key 映射回真实附件和 OA，用于区分“缓存内部重复”和“跨 OA 重复发票”。

`--limit` 只限制明细 examples 数量，不影响 summary count。生产判断以 summary 中的全量 count 和 `blocking_issue_count` 为准。

## 表状态

报告中的可选事实表会带 table status：

- `available`：表存在，count 为真实扫描结果。
- `missing`：表不存在或环境未部署对应 schema，count 固定为 0。

`missing` 不等同于业务数据为 0，也不会自动计入 blocking issue。出现 `missing` 时，先核对 migration/部署环境是否完整，再判断是否需要补库或跳过该业务域审计。

## 退出码

- `0`：没有 blocking issue。
- `1`：存在 blocking issue，需要人工处理后重跑。

Blocking issue 包含：

- 同一 canonical key 下出现多条正式发票。
- 同一 canonical key 下出现多条银行流水。
- 同一 canonical key 下出现多条 ETC 原始票。
- 同一 OA 附件票强 canonical key 出现在多个不同 OA 报销中。强 key 包含数电票号、发票代码+号码、附件稳定 hash；`seller_tax_no + buyer_tax_no + invoice_date + total_with_tax` 这类弱税额指纹不作为 OA 附件票 blocking key。
- 历史 `source_unique_key` 与当前 policy canonical key 不一致。

非 blocking warning：

- missing canonical 示例。
- suspected duplicate group。
- OA 附件票同一实际附件、同一 OA 内多个附件或历史 cache key 产生的重复 evidence。
- OA 附件票只命中弱税额指纹的跨 OA 疑似重复；必须人工核对发票号码、乘车人、行程等票面信息。

这些只用于人工排查，不自动阻断发布，也不自动合并历史对象。

## Repair 原则

- 先确认业务事实，再处理数据；不要只因为 key 相同就合并。
- canonical duplicate 优先查原始导入批次、附件来源、ETC 批次和税局认证记录。
- 修复应通过已有业务命令、专用 repair 工具或 migration 脚本完成，并保留审计记录。
- 修复完成后必须重新执行审计命令，确认 `blocking_issue_count=0`。

## 后续 read model 条件

只有当两个以上页面需要展示 duplicate group、canonical object 或 source lineage 时，才启用 `object_identity` read model。届时需要补齐 migration、worker registry、manifest/systemd env、health、backfill 和 source_versions。
