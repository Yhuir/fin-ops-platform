# Read Model 边界合同

本文件记录当前所有页面和资源 read model 的目标边界。可执行事实源是 `backend/src/fin_ops_platform/services/read_model_manifest.py` 与 `backend/src/fin_ops_platform/services/runtime_worker_registry.py`；本文档用于开发前审阅和变更后的长期维护。

扫描日期：2026-06-29。

## 全局目标态

普通页面 read model 必须符合 Partitioned + Scoped + Incremental Projection：

- Partitioned：刷新单位要落到业务分区，不能默认无界重建。常见分区包括月份、方向、来源、账号、页面 scope、父聚合 scope。
- Scoped：dirty scope、outbox event、worker refresh、query freshness/status 必须共享可验证 scope contract。
- Incremental Projection：写操作只污染受影响 scope；worker 投影只重算受影响范围，除非 manifest 明确把 all 定义为 fan-out 或可查询父聚合。

查询端必须经过 freshness/status/enqueue 边界；页面不能读取旧 read model 却返回 fresh。Redis 只能缓存 fresh gate 之后的 payload；RabbitMQ 只能作为可选 transport/wakeup，不能作为 read model 状态事实源。

## 当前验收状态

- 状态：PSCIP-L4 closed。
- 适用范围：当前 14 个 App Status read model。
- 例外语义：`workbench` 保留 active generation 原子发布；`bank_account_balance` 为 all-only projection；`pending_invoice` 使用 page-first explicit scopes 并拒绝裸 `all`；`cost_statistics` 使用 month shards plus queryable parent aggregate。
- 最终报告：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`。
- 生产证据：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`。
- 生产结果：scope contract `ok=true`、`violation_count=0`、current uncovered outbox failure count `0`；critical SLO grouped run 14/15 pass，唯一 Search miss targeted rerun pass。
- 残余风险：Search 单次 grouped-run 高延迟样本需继续观察；Workbench groups admin smoke 的 `400` 是 probe shape 问题，不是 stale-as-fresh 证据。

## Manifest 合同表

| Read model | Scope | Projection | `all` 语义 | Partition / Scope 说明 | Worker | Query owner | Repository owner | 权限边界 | 核心测试 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `workbench` | `workbench` | `active_generation_scoped_publish` | `active_month_shard_aggregate` | active generation + month shard；特殊原子发布模型 | `workbench` | `WorkbenchQueryFacade` | `PostgresReadModelRepository.workbench` | `workbench_api_session` | `tests/test_workbench_sql_runtime.py` |
| `workbench_relation` | `workbench_relation` | `scoped_incremental_distribution` | `fan_out_command` | 关系事实源按关联影响范围分发；跨月 relation 必须在每个受影响 scope 写入所有成员 row 索引，`rows` 唯一键为 `(tenant_id, scope_key, row_id)` | `workbench-relation` | `WorkbenchRelationReadFacade` | `WorkbenchRelationReadModelRepositoryPort` | `downstream_page_api_session` | `tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py` |
| `bank_detail` | `bank_detail` | `partitioned_scoped_incremental` | `fan_out_command` | 银行明细按页面 scope / 月份等业务范围刷新 | `bank-detail` | `BankDetailsApplicationService` | `BankDetailReadModelRepositoryPort` | `bank_details_api_session` | `tests/test_bank_details_sql_runtime.py` |
| `bank_account_balance` | `bank_account_balance` | `partitioned_scoped_incremental` | `fan_out_command` | 当前为 global all scope only | `bank-account-balance` | `BankDetailsApplicationService` | `BankAccountBalanceReadModelRepositoryPort` | `bank_details_api_session` | `tests/test_bank_account_balance_read_model.py` |
| `pending_invoice` | `pending_invoice` | `scoped_incremental` | `forbidden_bare_all` | `direction:filter_group[:YYYY-MM]` 页面 scope | `pending-invoice`；辅助 `search-pending` | `PendingInvoiceReadModelService` | `PendingInvoiceReadModelRepositoryPort` | `pending_invoices_api_session` | `tests/test_pending_invoice_service.py` |
| `search` | `search` | `partitioned_scoped_index` | `fan_out_command` | search source + month scope | `search`；辅助 `search-pending`、`search-secondary`、`search-tertiary` | Search read API | `SearchReadModelRepositoryPort` | `search_api_session` | `tests/test_search_pending_sql_runtime.py` |
| `invoice_lifecycle` | `invoice_lifecycle` | `scoped_incremental` | `fan_out_command` | 发票生命周期按受影响发票/方向 scope 刷新 | `invoice-lifecycle`；辅助 `invoice-lifecycle-secondary` | `InvoiceLifecycleReadFacade` | `InvoiceLifecycleReadModelRepositoryPort` | `invoice_lifecycle_page_api_session` | `tests/test_invoice_lifecycle_read_model_refresh.py` |
| `input_invoice_usage` | `input_invoice_usage` | `scoped_incremental` | `fan_out_command` | 进项发票使用情况按受影响 scope 刷新 | `invoice-usage-collection` | `InputInvoiceUsageReadModelService` | `InputInvoiceUsageReadModelRepositoryPort` | `input_invoice_usage_api_session` | `tests/test_input_invoice_usage_api.py` |
| `output_invoice_collection` | `output_invoice_collection` | `scoped_incremental` | `fan_out_command` | 销项发票收款情况按受影响 scope 刷新 | `invoice-usage-collection` | `OutputInvoiceCollectionService` | `OutputInvoiceCollectionReadModelRepositoryPort` | `output_invoice_collection_api_session` | `tests/test_output_invoice_collection_api.py` |
| `oa_pending_payment` | `oa_pending_payment` | `scoped_incremental` | `fan_out_command` | OA 待付款按受影响 scope 刷新 | `invoice-usage-collection` | `OaPendingPaymentReadModelService` | `OaPendingPaymentReadModelRepositoryPort` | `oa_pending_payment_api_session` | `tests/test_oa_pending_payment_api.py` |
| `cost_statistics` | `cost_statistics` | `partitioned_scoped_parent_rollup` | `queryable_parent_aggregate` | active/all month + parent aggregate；允许父聚合查询语义 | `cost-statistics`；辅助 `cost-tax` | `CostStatisticsQueryService` | `CostStatisticsReadModelRepositoryPort` | `cost_statistics_api_session` | `tests/test_cost_statistics_sql_runtime.py` |
| `tax_offset` | `tax_offset` | `partitioned_scoped_incremental` | `fan_out_command` | 税金抵扣按月份/业务 scope 刷新 | `tax-offset`；辅助 `cost-tax` | `TaxOffsetQueryService` | `TaxOffsetReadModelRepositoryPort` | `tax_offset_api_session` | `tests/test_tax_offset_sql_runtime.py` |
| `no_oa_bank_batch` | `no_oa_bank_batch` | `scoped_incremental` | `fan_out_command` | 免 OA 流水批次按批次/关联影响 scope 刷新 | `no-oa-bank-batch` | `NoOaBankBatchApplicationService` | `NoOaBankBatchReadModelRepositoryPort` | `no_oa_bank_batch_api_session` | `tests/test_no_oa_bank_batch_application_service.py` |
| `turnover_ledger` | `turnover_ledger` | `partitioned_scoped_incremental` | `fan_out_command` | 外部往来款按账期/主体/关联影响 scope 刷新 | `turnover-ledger` | `TurnoverLedgerQueryService` | `TurnoverLedgerReadModelRepositoryPort` | `turnover_ledger_api_session` | `tests/test_turnover_ledger_query_service.py` |

## 变更规则

- 新增 read model 时，必须先定义 manifest entry：scope、event type、worker、projection strategy、`all` 语义、query owner、repository owner、permission boundary 和测试入口。
- 修改 projection strategy 或 `all` 语义时，必须同步更新 scope policy、dirty scope 写入路径、worker registry、freshness/status 查询、API contract tests、worker/read model tests 和本文档。
- 删除旧 read model 代码前，必须证明没有页面、API、worker、测试或生产脚本继续读取旧路径。
- `workbench` 的 active generation 原子发布模型是明确例外，不允许机械迁移成普通 gateway 模型。
- 所有非事务 refresh 请求必须通过 `ReadModelRefreshGateway` / scope policy registry normalize、validate、dedupe 后进入 `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。
- 事务内 writer 可以在同一业务事务内写 dirty scope/outbox，但必须承担等价 scope contract，并有测试覆盖。

## 验收要求

Read model 重构或修复完成前，至少要完成：

- manifest 与 registry 一致。
- affected scopes 能从写操作进入 dirty scope/outbox。
- worker 能消费 event 并把目标 scope 投影为 fresh。
- API 查询能暴露 fresh/stale/refreshing 状态，不伪装 fresh。
- 页面能在写后读取到 fresh 数据，或明确显示刷新中/不可用状态。
- 相关旧链路没有继续被调用；旧代码若保留，必须有明确兼容理由和删除条件。
- 测试覆盖 read model/cache/worker、API contract、service orchestration 和受影响业务回归。
