# Read Model 边界合同

本文件记录当前所有页面和资源 read model 的目标边界。可执行事实源是 `backend/src/fin_ops_platform/services/read_model_manifest.py` 与 `backend/src/fin_ops_platform/services/runtime_worker_registry.py`；本文档用于开发前审阅和变更后的长期维护。

扫描日期：2026-07-03。

## 全局目标态

普通页面 read model 必须符合 Partitioned + Scoped + Incremental Projection：

- Partitioned：刷新单位要落到业务分区，不能默认无界重建。常见分区包括月份、方向、来源、账号、页面 scope、父聚合 scope。
- Scoped：dirty scope、outbox event、worker refresh、query freshness/status 必须共享可验证 scope contract。
- Incremental Projection：写操作只污染受影响 scope；worker 投影只重算受影响范围，除非 manifest 明确把 all 定义为 fan-out 或可查询父聚合。

查询端必须经过 freshness/status/enqueue 边界；页面不能读取旧 read model 却返回 fresh。Redis 只能缓存 fresh gate 之后的 payload；RabbitMQ 只能作为可选 transport/wakeup，不能作为 read model 状态事实源。
`job.outbox_events.available_at` 是 write-operation / read-model refresh enqueue-to-done SLO 的起点；事务内 refresh writer 必须用 statement-time `clock_timestamp()` 写 `available_at`/当前更新时间，不能让 PostgreSQL transaction-level `now()` 把业务写事务耗时污染到 worker drain 指标里。`created_at` 只保留为历史排序/兼容字段。

## Freshness / Version 合同

- 每个 read model scope 的 `source_versions` 必须覆盖自己的 projection schema version，以及构建该 payload 依赖的 canonical facts / upstream read model versions。
- 任何会改变 rows、groups、索引键、跨 scope 成员分发、状态字段、金额口径或 freshness 语义的 projection 行为变更，都必须 bump 自己的 projection schema version；不能只依赖事实表 `updated_at`。
- Worker 的 `source_versions_unchanged` 跳过优化只有在 own schema version 和全部依赖版本都匹配时才允许触发；缺失 schema/dependency version 时必须 fail closed 为 stale/refreshing 或执行重建。
- 下游 read model 消费 upstream read model 时，必须把 upstream source_versions 写入自身 scope source_versions。upstream schema/version 变化后，下游 scope 必须能被 freshness gate 识别并重新投影。
- `all` scope 不允许用一个伪全局版本掩盖月份 shard 差异；合法方式是 fan-out command、月份 shard convergence 或 manifest 明确登记的 parent aggregate。
- 页面和导出只能读取 freshness gate 之后的 payload；不得用 live fallback、旧 snapshot、Redis 或前端拼接把 stale read model 伪装成 fresh。
- `pending_invoice` 的 source summary 与 `filter=all` expected source versions 必须从 `app.bank_transactions` canonical facts 识别范围；不能只从 `read_model.pending_invoice_rows` 反推，否则新导入事实源没有投影行时会漏判 fresh 或显示旧“全部流水”数。父 scope status 必须聚合子月份 dirty scope。

## 当前验收状态

- 状态：Read Model 模块化 PSCIP-L4 closed；full external PSCIP-L4 / 高性能全域闭环 open。
- 适用范围：当前 15 个 App Status read model；`bank_flow_rule_batch` 已登记为独立可执行 manifest/worker。流水规则批量处理对外使用 `bank_flow_rule_batch` operation target，freshness/readiness/outbox/worker 直接使用 `bank_flow_rule_batch` scope/event；mutation 和 refresh persistence 走 bank-flow 命名 IO，submit/withdraw mutation 不同步读取或写入 Workbench read model snapshot，PostgreSQL 运行时查询 `read_model.bank_flow_rule_batch_rows`。no-OA legacy 继续使用 `read_model.no_oa_bank_batch_rows`。
- 例外语义：`workbench` 保留 active generation 原子发布；`bank_account_balance` 为 all-only projection；`pending_invoice` 使用 page-first explicit scopes 并拒绝裸 `all`；`cost_statistics` 使用 month shards plus queryable parent aggregate。
- 最终报告：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`。
- 生产证据：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`。
- 生产结果：scope contract `ok=true`、`violation_count=0`、current uncovered outbox failure count `0`；critical SLO grouped run 14/15 pass，唯一 Search miss targeted rerun pass。
- 2026-07-03 复核：生产 release `pscip-l4-workbench-group-row-min-20260703` 上 `/health/ready` ready，required worker missing/stale/mismatch 为 `0/0/0`，Workbench lane 排除 `all`、`workbench-aggregate` lane 只 claim `all`。Workbench generation payload owner 已收口：active `workbench:2026-02` snapshot/group/group_rows payload 中 `oa_rows/bank_rows/detail_fields/summary_fields` 放大计数为 `0`，完整行详情只保留在 `workbench_rows.payload`。Workbench warmed targeted 1s direct SLO `10/10` pass，p95/max `890.808ms`；成本统计 `active:2026-02` targeted `5/5` pass，p95/max `938.124ms`。
- 2026-07-03 后续复核：release `pscip-l4-search-index-noop-20260703` 将 Search index 保存改为 row-level no-op upsert + stale-row delete 后，`search:2026-03` targeted 1s direct SLO `10/10` pass，最大 enqueue-to-fresh `666.731ms`、最大 handler `231.055ms`。release `pscip-l4-invoice-defer-20260703` 将 `invoice_lifecycle` upstream dependency dirty 状态改为 dependency defer 后，grouped run 中 `invoice_lifecycle:2026-02` handler 从约 `1939.958ms` 降到 `300.036ms`，但总耗时仍 `1067.206ms`。本地新增 `0086_runtime_queue_claim_hot_path.sql`，为 runtime worker lane claim 增加 `(event_type,status,priority_rank,available_at,created_at,id)` active-queue 索引，用于收敛 grouped run 的 pickup/claim 长尾；该索引尚未发布到生产复测。
- 残余风险：full critical grouped 1s smoke 仍未闭环，最新生产复测为 `14/16` pass，失败项为 `workbench:2026-02` 总耗时 `1387.983ms` / handler `886.787ms`，以及 `invoice_lifecycle:2026-02` 总耗时 `1067.206ms` / handler `300.036ms`。Search targeted 已闭合，不再是当前 blocker。真实 write-operation confirm/withdraw/no-OA withdraw 当前 release 样本仍未闭合，因此 full external PSCIP-L4 和“所有页面耗时短”仍 open。

## Manifest 合同表

| Read model | Scope | Projection | `all` 语义 | Partition / Scope 说明 | Worker | Query owner | Repository owner | 权限边界 | 核心测试 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `workbench` | `workbench` | `active_generation_scoped_publish` | `active_month_shard_aggregate` | active generation + month shard；特殊原子发布模型；月份 shard 由 `workbench` lane 消费，`all` 聚合由 `workbench-aggregate` lane 消费，避免低优先级全局聚合阻塞页面首屏 shard refresh；`all` shard 枚举必须包含 active 月度 generation，query freshness/status 必须检查父 generation 与 `all` generation 的 source_version/row/group 基本一致性，父 scope 有内容而 `all` 缺失或为空时必须 stale+enqueue，不能返回 fresh 空结果 | `workbench` / `workbench-aggregate` | `WorkbenchQueryFacade` | `PostgresReadModelRepository.workbench` | `workbench_api_session` | `tests/test_workbench_sql_runtime.py`、`tests/test_runtime_worker_registry.py` |
| `workbench_relation` | `workbench_relation` | `scoped_incremental_distribution` | `fan_out_command` | 关系事实源按关联影响范围分发；跨月 relation 必须在每个受影响 scope 写入所有成员 row 索引，`rows` 唯一键为 `(tenant_id, scope_key, row_id)`。关联台 confirm/withdraw 主链路由 `WorkbenchWriteUnitOfWork` 显式写 `workbench_relation` 与 downstream refresh targets，repository 只持久化 relation facts | `workbench-relation` | `WorkbenchRelationReadFacade` | `WorkbenchRelationReadModelRepositoryPort` | `downstream_page_api_session` | `tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_workbench_uow_contract.py` |
| `bank_detail` | `bank_detail` | `partitioned_scoped_incremental` | `fan_out_command` | 银行明细按页面 scope / 月份等业务范围刷新 | `bank-detail` | `BankDetailsApplicationService` | `BankDetailReadModelRepositoryPort` | `bank_details_api_session` | `tests/test_bank_details_sql_runtime.py` |
| `bank_account_balance` | `bank_account_balance` | `partitioned_scoped_incremental` | `fan_out_command` | 当前为 global all scope only | `bank-account-balance` | `BankDetailsApplicationService` | `BankAccountBalanceReadModelRepositoryPort` | `bank_details_api_session` | `tests/test_bank_account_balance_read_model.py` |
| `bank_flow_rule_batch` | `bank_flow_rule_batch` | `scoped_incremental` | `fan_out_command` | 流水规则批量处理按 month scope 刷新；route/service/worker/barrier/producer/repository/persistence IO 独立，PostgreSQL read model 行存储为 `read_model.bank_flow_rule_batch_rows`，持久化按 scope 批量 values upsert；submit/withdraw mutation 只同步保存 relation fact 和受影响月份 bank-flow batch scope，禁止同步保存 Workbench read model snapshot；迁移 `0082_bank_flow_rule_batch_storage.sql` 只负责从历史 no-OA 表回填旧 bank-flow rows；submit/withdraw/reset 的 operation barrier 除自身 month scope 外，还必须返回 `workbench_relation`、`workbench` 的 `all` + 受影响 month scope，保护关联台 `month=all` 可见性 | `bank-flow-rule-batch` | `BankFlowRuleBatchApplicationService` | `BankFlowRuleBatchReadModelRepositoryPort` | `bank_flow_rule_batch_api_session` | `tests/test_bank_flow_rule_batch_backend_boundary.py`、`tests/test_bank_flow_rule_batch_application_service.py`、`tests/test_operation_freshness_barrier.py`、`tests/test_postgres_repositories_boundaries.py` |
| `pending_invoice` | `pending_invoice` | `scoped_incremental` | `forbidden_bare_all` | `direction:filter_group[:YYYY-MM]` 页面 scope；父 scope 查询必须聚合子月份 dirty status；source summary 与 `filter=all` source-version 依赖月份来自 `app.bank_transactions` canonical facts；银行流水导入的 pending scope 由共享 planner 从 cost scope + bank_detail scope 合并生成 | `pending-invoice`；辅助 `search-pending` | `PendingInvoiceReadModelService` | `PendingInvoiceReadModelRepositoryPort` | `pending_invoices_api_session` | `tests/test_pending_invoice_service.py`、`tests/test_search_pending_sql_runtime.py`、`tests/test_import_processing_service.py` |
| `search` | `search` | `partitioned_scoped_index` | `fan_out_command` | search source + month scope | `search`；辅助 `search-pending`、`search-secondary`、`search-tertiary` | Search read API | `SearchReadModelRepositoryPort` | `search_api_session` | `tests/test_search_pending_sql_runtime.py` |
| `invoice_lifecycle` | `invoice_lifecycle` | `scoped_incremental` | `fan_out_command` | 发票生命周期按受影响发票/方向 scope 刷新 | `invoice-lifecycle`；辅助 `invoice-lifecycle-secondary` | `InvoiceLifecycleReadFacade` | `InvoiceLifecycleReadModelRepositoryPort` | `invoice_lifecycle_page_api_session` | `tests/test_invoice_lifecycle_read_model_refresh.py` |
| `input_invoice_usage` | `input_invoice_usage` | `scoped_incremental` | `fan_out_command` | 进项发票使用情况按受影响 scope 刷新 | `invoice-usage-collection` | `InputInvoiceUsageReadModelService` | `InputInvoiceUsageReadModelRepositoryPort` | `input_invoice_usage_api_session` | `tests/test_input_invoice_usage_api.py` |
| `output_invoice_collection` | `output_invoice_collection` | `scoped_incremental` | `fan_out_command` | 销项发票收款情况按受影响 scope 刷新；linked 多销项发票 relation 投影为单条净额收款行，负数/红字成员保留在 relation summaries | `invoice-usage-collection` | `OutputInvoiceCollectionService` | `OutputInvoiceCollectionReadModelRepositoryPort` | `output_invoice_collection_api_session` | `tests/test_output_invoice_collection_api.py` |
| `oa_pending_payment` | `oa_pending_payment` | `scoped_incremental` | `fan_out_command` | OA 待付款按受影响 scope 刷新；跨月 relation 可在多个 month shard 存在物理行，默认 `all` 查询必须按 `row_id` 去重为业务行后再计算 rows、分页、summary 和 viewCounts；生产查询 API 必须经 `OaPendingPaymentReadModelService` freshness/status 边界，service 缺失时 fail closed，不回退 live query 或 snapshot relation inference | `invoice-usage-collection` | `OaPendingPaymentReadModelService` | `OaPendingPaymentReadModelRepositoryPort` | `oa_pending_payment_api_session` | `tests/test_oa_pending_payment_api.py`、`tests/test_platform_runtime_boundary_guards.py` |
| `cost_statistics` | `cost_statistics` | `partitioned_scoped_parent_rollup` | `queryable_parent_aggregate` | active/all month + parent aggregate；月份 shard 只消费 Workbench active generation，父 scope 从成本统计物化 shard 聚合；允许父聚合查询语义；project/detail/export/export-preview API 由 `CostStatisticsQueryService` 从 fresh explorer read model 组装，read model non-fresh 返回 `409 cost_statistics_read_model_not_fresh`，不得由 route 回退旧 live service | `cost-statistics` | `CostStatisticsQueryService` | `CostStatisticsReadModelRepositoryPort` | `cost_statistics_api_session` | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_platform_runtime_boundary_guards.py` |
| `tax_offset` | `tax_offset` | `partitioned_scoped_incremental` | `fan_out_command` | 税金抵扣按月份/业务 scope 刷新 | `tax-offset`；辅助 `cost-tax` | `TaxOffsetQueryService` | `TaxOffsetReadModelRepositoryPort` | `tax_offset_api_session` | `tests/test_tax_offset_sql_runtime.py` |
| `no_oa_bank_batch` | `no_oa_bank_batch` | `scoped_incremental` | `fan_out_command` | 免 OA 流水批次按批次/关联影响 scope 刷新；查询缺 SQL read model repository 时 fail-closed，不回退旧 snapshot fresh；共享迁移底座内的 month/all scope save 只能替换 `relation_mode=no_oa_bank_batch` rows，必须保留同 scope bank-flow rows，持久化按 scope 批量 values upsert | `no-oa-bank-batch` | `NoOaBankBatchApplicationService` | `NoOaBankBatchReadModelRepositoryPort` | `no_oa_bank_batch_api_session` | `tests/test_no_oa_bank_batch_application_service.py`、`tests/test_no_oa_bank_batch_service.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py` |
| `turnover_ledger` | `turnover_ledger` | `partitioned_scoped_incremental` | `fan_out_command` | 外部往来款按账期/主体/关联影响 scope 刷新 | `turnover-ledger` | `TurnoverLedgerQueryService` | `TurnoverLedgerReadModelRepositoryPort` | `turnover_ledger_api_session` | `tests/test_turnover_ledger_query_service.py` |

## 下游页面特化读 I/O

- `workbench_relation` 的通用查询 owner 仍是 `WorkbenchRelationReadFacade`。下游页面只能通过 facade/repository port 读取 freshness-gated payload，不能直接读 `read_model.workbench_relation_*` 表。
- `batch-accounting` 的未提交首屏只允许调用候选 row-id relation lookup 和 `count_batch_accounting_relations_by_year(year)`；该 count I/O 归属 `workbench_relation` repository port，返回年份级 submitted count 和 read model freshness/status，不返回 relation DTO。
- `batch-accounting` 的已提交 bucket 必须调用 `list_batch_accounting_relations_by_year(year)` 一次读取年份内 batch-accounting relation groups；该 I/O 归属 `workbench_relation` repository port，返回 relation DTO 和 read model freshness/status。禁止按 12 个月循环 list，也禁止把该路径复用于未提交首屏 summary。

## 变更规则

- 新增 read model 时，必须先定义 manifest entry：scope、event type、worker、projection strategy、`all` 语义、query owner、repository owner、permission boundary 和测试入口。
- 修改 projection strategy 或 `all` 语义时，必须同步更新 scope policy、dirty scope 写入路径、worker registry、freshness/status 查询、API contract tests、worker/read model tests 和本文档。
- 修改 projection 行为或 upstream dependency 合同时，必须 bump 对应 projection schema version，并新增回归测试证明旧 source_versions 不会触发 `source_versions_unchanged` 跳过。
- 删除旧 read model 代码前，必须证明没有页面、API、worker、测试或生产脚本继续读取旧路径。
- `workbench` 的 active generation 原子发布模型是明确例外，不允许机械迁移成普通 gateway 模型。
- 所有非事务 refresh 请求必须通过 `ReadModelRefreshGateway` / scope policy registry normalize、validate、dedupe 后进入 `RuntimeQueueRepository.enqueue_read_model_refresh(...)`。
- 事务内 writer 可以在同一业务事务内写 dirty scope/outbox，但必须承担等价 scope contract，并有测试覆盖；当一次业务写入会污染多个 target 时，必须先收集 refresh intents，再批量写 `job.read_model_dirty_scopes` 和 `job.outbox_events`，避免 per-target `fetch_one + execute` 放大提交耗时。
- Workbench confirm/withdraw 的事务内 writer owner 是 `WorkbenchWriteUnitOfWork`；`Application._workbench_uow_repository_factory(...)` 必须注入 `PostgresWorkbenchRelationRepository(transaction, enqueue_refreshes=False)`。新增 downstream read model 必须扩展 `refresh_metadata.downstream_scope_types` / target planner 和测试，禁止把旧 repository hidden fan-out 放回生产主链路。UoW 可通过 `RuntimeQueueReadModelRefreshWriter.enqueue_refreshes(...)` 批量写 dirty scope/outbox，以减少同一业务事务内多 target 写入的 SQL 往返；批量接口不得改变 `job.read_model_dirty_scopes` / `job.outbox_events` 的 source_version、dedupe、priority、trace_id 和 readiness 事实源语义，并必须保持 `available_at` 表示实际入队可处理时间。

## 验收要求

Read model 重构或修复完成前，至少要完成：

- manifest 与 registry 一致。
- affected scopes 能从写操作进入 dirty scope/outbox。
- worker 能消费 event 并把目标 scope 投影为 fresh。
- API 查询能暴露 fresh/stale/refreshing 状态，不伪装 fresh。
- 页面能在写后读取到 fresh 数据，或明确显示刷新中/不可用状态。
- 相关旧链路没有继续被调用；旧代码若保留，必须有明确兼容理由和删除条件。
- 测试覆盖 read model/cache/worker、API contract、service orchestration 和受影响业务回归。
