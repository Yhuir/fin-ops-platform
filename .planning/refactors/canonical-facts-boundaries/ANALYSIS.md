# Canonical Facts 全量分析

日期：2026-06-28

## 核心判断

“统一事实源”在本仓库中不是 read model，也不是一个新 `UnifiedFactSource` runtime service。它是 PostgreSQL canonical facts + 拥有这些 facts 的业务模块。

边界和 I/O 清楚只能降低模块互相干扰；真正闭环还需要 owner、禁止路径、旧代码删除、写后 downstream 合同、测试/静态 guard 和长期文档一致。

## 事实分层

| 层 | 示例 | 规则 |
| --- | --- | --- |
| 外部事实 | OA Mongo、Excel/PDF/ZIP、银行导出 | app 只读接入或导入，不写外部原始库。 |
| Canonical facts | `app.invoices`、`app.bank_transactions`、`app.workbench_pair_relations` | 业务唯一真相，必须有业务 owner。 |
| Runtime/audit facts | `job.outbox_events`、`job.read_model_dirty_scopes`、`audit.events` | 描述刷新、任务、审计，不替代业务事实。 |
| Read models | `read_model.*` | 派生投影，由 07 read model closure 管理。 |
| Cache/transport/UI hints | Redis、RabbitMQ、frontend events | 只做缓存、唤醒、传输或提示。 |

## Canonical Fact Families

| Fact family | 主要表 | Owner module | 当前 closure |
| --- | --- | --- | --- |
| 导入批次和文件 | `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` | `imports-invoices`、`imports-bank-transactions`、`imports-etc-invoices` | PSCF-L0 |
| 统一发票池 | `app.invoices` | `imports-invoices` / canonical invoice pool | PSCF-L0 |
| 银行流水 | `app.bank_transactions` | `imports-bank-transactions` + `bank-details` | PSCF-L0 |
| 银行分类和标签 | `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`app.bank_transaction_category_confirmations` | `bank-details` | PSCF-L0 |
| Workbench 关系事实 | `app.workbench_pair_relations`、`app.workbench_pair_relation_history` | `workbench-relations` | PSCF-L0 |
| Workbench 操作事实 | `app.workbench_row_overrides`、`app.workbench_exception_cases`、`app.matching_runs`、`app.matching_results`、`app.workbench_idempotency_records` | `reconciliation-workbench` | PSCF-L0 |
| 免 OA 批次 | `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events` | `no-oa-bank-batches` | PSCF-L0 |
| OA 投影和附件缓存 | `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`、`app.oa_sync_*`、`app.oa_attachment_invoice_cache*`、`app.manual_oa_imports` | `oa-integration` | PSCF-L0 |
| 税金事实 | `app.tax_certified_import_*`、`app.tax_offset_plans` | `tax-offset` | PSCF-L0 |
| ETC 事实 | `app.etc_*`、`app.etc_batch_invoice_links` | `etc-tickets` / `imports-etc-invoices` | PSCF-L0 |
| 外部往来款 | `app.turnover_relations`、`app.turnover_relation_events`、`app.turnover_ledger_extras` | `turnover-ledger` | PSCF-L0 |
| 销项收款生命周期 | `app.output_invoice_collection_*`、`app.output_invoice_receipts`、`app.output_invoice_receipt_events` | `output-invoice-collections` | PSCF-L0 |
| 进项使用 OA 冲销 | `app.input_invoice_usage_oa_reverse_batches` | `input-invoice-usage` | PSCF-L0 |
| OA 待付款银行关系 | `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims`、`app.oa_pending_payment_bank_relation_events` | `oa-pending-payments` | PSCF-L0 |
| 设置和凭证 | `app.app_settings`、`app.oa_applicant_credentials` | `settings` / `oa-integration` | PSCF-L0 |

## 旧代码风险

当前扫描仍发现 legacy/fallback 关键词集中在：

- `runtime_bootstrap.py` 的 legacy full snapshot 限制逻辑。
- ETC legacy batch/service 文档和代码。
- turnover legacy fallback adapters。
- no-OA legacy repair/consolidation。
- workbench legacy confirmed/settled 状态映射。

这些路径后续必须逐项分类并删除生产主链路。保留 migration/audit/rollback 工具不算 closure。

## 07 Read Model 冲突边界

本工作流不得修改 07-owned runtime 文件，包括 read model manifest、scope policy、refresh/query gateway、runtime queue、worker registry、operation barrier、read model repository 和 `docs/modules/read-models/`。需要这些改动时记录 `blocked-by-read-model-controller`。
