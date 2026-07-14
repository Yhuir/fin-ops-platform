# 对象身份与去重规则审计

本文档描述业务对象 identity/dedup 的生产审计方式。当前闭环统一规则入口，并在 workbench active generation 中投影对象身份字段；仍不启用独立的 `object_identity` 分发 read model。

## 规则边界

- 统一入口是 `FinancialObjectIdentityPolicy`、`ObjectDedupDecisionService` 和 repository 查询边界。
- 发票、银行流水、OA 附件票、ETC 发票、税局认证记录和导入预览行不得在页面 service、parser、server 或运维工具中私有拼 identity key。
- `InvoiceIdentityService` 和 `BankTransactionIdentityService` 是底层兼容策略，可以被 policy 复用。
- `source_unique_key`、`data_fingerprint` 和现有唯一索引继续保留。
- Workbench 展示状态由 `WorkbenchObjectIdentityArbitrationService` 在分组前仲裁：正式发票与 OA 附件发票命中同一强发票 identity 时，只允许进入一个最终展示区。
- 强发票 identity 只包含数电发票号、发票代码+号码。税额指纹、金额、项目、申请人、对方名称等弱字段只用于审计提示，不用于自动跨来源合并。
- 银行流水只有在稳定 business-fields identity 完整且其中一条已被 paired/异常/忽略占用时，才压制同 identity 的 unpaired 别名；全 unpaired 重复只审计。
- OA 单据以 `row_id` 为主身份，`form_id`/`workflow_no` 只作为 alias 审计线索，不按金额、申请人或项目推断合并。
- OA source alias 只能来自 `app.oa_source_aliases.status='active'` 的显式审计事实；用于把同一 OA 生命周期中的旧 source row 归一到 canonical row，不删除 OA 原始投影、附件或 cache。
- 历史冲突不做破坏性合并。审计输出报告，人工 repair 或 read model rebuild 后再重新审计。

## 生产审计命令

在服务器发布完成、环境变量指向生产 PostgreSQL 后执行：

```bash
cd /path/to/fin-ops-platform
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.audit_object_identity --json --limit 50
```

可限定 workbench active generation scope：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.audit_object_identity \
  --json \
  --limit 50 \
  --workbench-scope 2026-02
```

报告覆盖：

- `app.invoices`：正式发票 canonical key、stored key mismatch、duplicate canonical、missing canonical；其中 blocking 只看数电发票号、发票代码+号码这两类强 identity，税额指纹只作为 warning。
- `app.bank_transactions`：银行流水 canonical key、stored key mismatch、duplicate canonical、missing canonical。
- `app.etc_invoices`：ETC 原始票 canonical key、duplicate canonical、missing canonical。该表是原始来源事实，重复只作为 warning；正式发票是否重复以 canonical `app.invoices` 为准。
- `app.invoices.etc_invoice_id`：已关联到统一发票池既有 canonical 发票的 ETC metadata 数量。
- `app.oa_attachment_invoice_cache`：OA 附件票缓存中的正式发票 evidence/invoices canonical、suspected duplicate、missing canonical。
- `app.oa_attachment_invoice_cache_sources` / `app.oa_attachments`：将 OA 附件票缓存 key 映射回真实附件和 OA，用于区分“缓存内部重复”和“跨 OA 重复发票”。
- `app.oa_source_aliases`：只读取 `active` alias，将已确认的 OA lifecycle/migration alias 归一到 canonical OA row；缺表或无 active alias 时保持原判定。
- `read_model.workbench_group_rows` active generation：同一强发票 identity 或稳定银行 identity 是否同时存在于 `paired` 和 `unpaired` zone。
- `read_model.workbench_group_rows` active generation：同一 row id 或同一强发票 identity 是否在多个 unpaired group 中同时成为 visible/operable owner；银行流水 unpaired/unpaired 只按 row id 审计，不按稳定 business-fields identity 阻断。
- `app.oa_applications`：同一 `form_id` 是否映射多个 `row_id`，用于排查 OA alias 风险。
- `app.workbench_pair_relations`：active relation 中是否存在指向已不存在对象的 row_id。

## Workbench relation 展示归属审计

对象 identity 审计负责发现同一业务对象是否有多个 visible owner；active relation 写入后是否已经在当前 Workbench active generation 中同组展示，由统一 `reconciliation-workbench` 页面 Audit 覆盖。管理员页面按钮和下列 CLI 调用同一个只读 proof core；CLI 只是运维适配器，不是第二套审计实现。发布前或生产修复后执行：

```bash
cd /path/to/fin-ops-platform
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.audit_workbench_relation_display --json --limit 50
```

该工具只执行 `select`，不写 `app.*`、`read_model.*` 或 `job.*`。同一报告还检查 canonical/shared typed-edge equality、`workbench`/`workbench_relation` dirty scope 和 outbox；Workbench display 检查包括：

- `app.workbench_pair_relations` 中 active relation 的成员 row 是否存在于 active Workbench `all` generation。
- 同一 relation 的成员 row 在 `all` 或成员月份 scope 中是否被拆到多个 group。
- 同一 relation row 在同一个 active scope 中是否有多个 visible owner。
- row payload 中的 `case_id` / `relation_mode` 是否与 canonical relation 不一致。
- `all` generation 是否旧于 relation 成员所在月份 generation。
- active relation members 是否精确等于 paired members，以及其余 canonical facts 是否各自成为唯一 unpaired owner；历史 metadata 不得改变归属。

出现 blocking issue 时，不要直接修改 `read_model.workbench_group_rows` 或 `read_model.workbench_generations`。修复必须走现有刷新边界：按 relation 成员月份通过 `ReadModelRefreshGateway` / 事务内 repository scope contract 入队 Workbench month refresh，再用 aggregate-only `all` refresh 收敛全局 active generation。修复后重跑统一页面 Audit 和对象 identity 审计，确认页面报告 `integrity=pass`、`freshness=fresh`、`queue=drained` 且 `blocking_issue_count=0`。

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

- 同一强发票 identity 下出现多条正式发票。强 identity 只包含数电发票号、发票代码+号码。
- 同一 canonical key 下出现多条银行流水。
- 同一 OA 附件票强 canonical key 出现在多个不同 OA 报销中。强 key 包含数电票号、发票代码+号码、附件稳定 hash；`seller_tax_no + buyer_tax_no + invoice_date + total_with_tax` 这类弱税额指纹不作为 OA 附件票 blocking key。
- 历史 `source_unique_key` 与当前强发票或银行 policy canonical key 不一致。正式发票弱税额指纹 mismatch 不阻断发布。
- Workbench active generation 中同一强发票 identity 或稳定银行 identity 同时出现在 `paired` 与 `unpaired`。
- Workbench active generation 中同一 row id 或同一强发票 identity 同时出现在多个 unpaired group，导致同一事实有多个 visible/operable owner。
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
- `repair_workbench_pair_relation_integrity` 生产执行必须先 dry-run，并用可重复的 `--case-id <exact-case-id>`
  把写入限制到本轮 `audit_object_identity.workbench_identity_audit.orphan_relation_groups` 已确认的 case；
  禁止因为全量 dry-run 同时发现其它历史关系变化就直接无范围执行 `--execute`。执行后必须复跑对象身份审计，
  再通过 `ReadModelRefreshGateway` 重建受影响 `workbench_relation`、`invoice_lifecycle` 和页面 read model。
- OA lifecycle/migration alias 修复优先写入 `app.oa_source_aliases`，并以 `active` 状态受控启用；禁止为了让审计通过而删除 `app.oa_applications`、`app.oa_attachments`、`app.oa_attachment_invoice_cache*` 或手工伪造 read model readiness。
- 修复或发布后必须重建受影响 workbench/workbench_relation scope，再重新执行审计命令，确认 `blocking_issue_count=0`。
- relation display 不一致的生产修复只能入队刷新或使用专用 repair 工具重新触发 canonical scope contract；禁止手改 read model 投影行。

## 历史治理记录

- 2026-06-30：生产登记 3 条 `active` OA source alias，覆盖 `oa-exp-69898450db8c0a3633bd748c -> oa-exp-2005`、`oa-exp-69a7aeaedb8c0a3633bd74a7 -> oa-exp-2035`、`oa-exp-69c0b43adb8c0a3633bd74c4 -> oa-exp-2062`。固定入口 `workbench-audit-identity` 复核 `blocking_issue_count=0`、`oa_attachment_invoice_blocking_duplicate_group_count=0`，未删除 OA 投影、附件、附件票 cache 或 read model 行。

## 后续 read model 条件

本轮只在 workbench 投影表增加 nullable identity columns，不新增独立 object identity read model 或 worker。只有当两个以上页面需要展示 duplicate group、canonical object 或 source lineage 时，才启用独立 `object_identity` read model。届时需要补齐 migration、worker registry、manifest/systemd env、health、backfill 和 source_versions。
