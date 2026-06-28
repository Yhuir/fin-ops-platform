# Canonical Facts Boundary Analysis

日期：2026-06-26

## 分析范围

本轮只做文档和边界分析，不改运行时代码。读取来源包括：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/persistence-and-read-models.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/read-models/*`
- `docs/modules/workbench-relations/boundary-io.md`
- PostgreSQL migrations `backend/src/fin_ops_platform/postgres/migrations/*.sql`
- 关键 repository/service 文件和已有 GSD read model closure 记录

## 核心判断

用户定义的“统一事实源”是业务唯一真相，即 PostgreSQL canonical facts + 各业务模块 owner。它不是 read model。

当前 read model 治理已经比较完整：manifest、scope policy、query gateway、refresh gateway、runtime queue、worker registry 和 App Status readiness 已成型。缺口在写侧源事实：各业务 facts 的 owner、允许写入口、允许读入口、下游 dirty/outbox 和禁止绕过路径需要在模块边界中明确。

## 事实分层

| 层 | 示例 | Owner | 说明 |
| --- | --- | --- | --- |
| 外部事实 | OA Mongo、银行/发票 Excel、ETC ZIP/PDF/XML | 外部系统或导入文件 | app 只能只读接入或导入，不写外部原始事实。 |
| Canonical facts | `app.invoices`、`app.bank_transactions`、`app.workbench_pair_relations`、`app.etc_business_batches` | 现有业务模块 | 业务唯一真相，写入必须经过 owner 边界。 |
| Runtime facts | `job.outbox_events`、`job.read_model_dirty_scopes`、`job.background_jobs`、worker heartbeat | runtime/read-models/workers | 描述异步刷新和任务状态，不是业务事实本体。 |
| Read models | `read_model.*` 页面投影和 readiness | read-models + 各投影 owner | 派生投影，不反向成为业务事实源。 |
| Cache/event hints | Redis payload、RabbitMQ、前端 domain event | runtime/UI | 只做缓存、transport 或刷新提示。 |

## 当前 canonical fact owner 初表

| 事实族 | 主要表 | 当前 owner | 主要写入口 | 下游输出 |
| --- | --- | --- | --- | --- |
| 导入批次和文件 | `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` | imports 模块族 | import preview/confirm/job、file object migration | import job、workbench/search/bank/detail/tax/cost dirty scopes |
| 统一发票池 | `app.invoices` | imports-invoices / canonical invoice pool | `ImportNormalizationService`、受控 OA/ETC existing-link 路径 | workbench、pending invoice、invoice lifecycle、tax、cost、search |
| 银行流水 | `app.bank_transactions` | imports-bank-transactions + bank-details | 银行流水导入确认、bank import job | bank_detail、workbench、turnover、no-OA、search |
| 银行分类/标签 | `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`app.bank_transaction_category_confirmations` | bank-details | bank detail category/rule services | bank_detail、turnover_ledger、no_oa_bank_batch、search、workbench |
| 关联关系 | `app.workbench_pair_relations`、`app.workbench_pair_relation_history` | workbench-relations | `WorkbenchRelationCommandService` / UoW | workbench_relation、workbench、pending invoice、invoice usage、OA pending、tax、cost、search |
| Workbench 操作事实 | `app.workbench_row_overrides`、`app.workbench_exception_cases`、`app.matching_runs`、`app.matching_results`、`app.workbench_idempotency_records` | reconciliation-workbench | workbench command/facade services | workbench active generation、workbench_relation、search/cost/tax as applicable |
| 免 OA 批次 | `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events` | no-oa-bank-batches | `NoOaBankBatchApplicationService` | no_oa_bank_batch、workbench_relation、turnover_ledger、search |
| OA 投影和附件缓存 | `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`、`app.oa_sync_*`、`app.oa_attachment_invoice_cache*`、`app.manual_oa_imports` | oa-integration | OA sync worker、manual OA import service | workbench、pending invoice、OA pending、invoice lifecycle、search |
| 税金事实 | `app.tax_certified_import_*`、`app.tax_offset_plans` | tax-offset | certified import confirm、tax plan service | tax_offset、cost_statistics、invoice_lifecycle |
| ETC 事实 | `app.etc_invoices`、`app.etc_import_*`、`app.etc_submission_batches`、`app.etc_business_batches`、`app.etc_reconciliation_*`、`app.etc_batch_invoice_links` | etc-tickets / imports-etc-invoices | ETC import、business batch service、historical repair tools | workbench、workbench_relation、tax/cost/search as applicable |
| 外部往来款 | `app.turnover_relations`、`app.turnover_relation_events`、`app.turnover_ledger_extras` | turnover-ledger | turnover write facade/UoW | turnover_ledger、workbench_relation、workbench、cost、search |
| 销项收款生命周期 | `app.output_invoice_collection_*`、`app.output_invoice_receipts`、`app.output_invoice_receipt_events` | output-invoice-collections | output invoice collection lifecycle services | output_invoice_collection、invoice_lifecycle、workbench_relation |
| 进项使用 OA 冲销 | `app.input_invoice_usage_oa_reverse_batches` | input-invoice-usage | OA reverse service | input_invoice_usage、invoice_lifecycle、workbench_relation |
| OA 待付款银行关系 | `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims`、`app.oa_pending_payment_bank_relation_events` | oa-pending-payments | OA pending payment relation service | oa_pending_payment、bank_detail、turnover_ledger、workbench_relation |
| 设置和凭证 | `app.app_settings`、`app.oa_applicant_credentials` | settings / oa-integration | settings service、credential service | affected read model dirty scopes by setting family |
| Runtime 和审计 | `job.*`、`audit.*` | runtime-workers、read-models、permissions-and-audit | queue/background/audit services | App Status、operation barrier、SLO evidence |

## 发现的主要差距

1. 现有文档对 read model 的 owner、scope 和 freshness 记录很完整，但 canonical facts 的 owner 矩阵此前不集中。
2. 部分 shared repository 仍承担过渡期 owner，例如 `PostgresCoreRepository`、`PostgresWorkbenchRepository`、`PostgresReadModelRepository`。文档需要约束“共享 SQL owner 不是共享业务 owner”。
3. 历史 snapshot、local fallback、repair/migration tools 仍存在，必须明确只能作为 migration/shadow/audit/rollback 或受控工具，不得进入 production API 主路径。
4. 写操作的 read model 输出已经在部分模块中有 `freshness_targets` / operation barrier，但全局 closure 记录仍显示需要逐页面证明。
5. `read-models` 模块明确“不拥有源业务事实”，因此 canonical facts 必须由现有业务模块接住，不能只依赖 read model governance。

## 文档影响

本轮稳定结论需要落到：

- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/modules/canonical-facts/README.md`
- `docs/modules/canonical-facts/boundary-io.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/modules/README.md`
- `docs/index.md`

后续代码重构时，再按影响范围更新每个业务模块的 `boundary-io.md`。
