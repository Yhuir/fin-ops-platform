# Read Model Manifest 与边界库存

**日期:** 2026-06-23
**Boundary:** `read-models:manifest-and-boundary-inventory`
**状态:** `closed-autonomous`
**范围:** 只做 read model manifest / owner / IO / state / event / permission / test inventory；不改业务代码，不做 Go/Fiber，不做生产写入，不拆 SQL 大文件。

## 执行结论

当前代码已经具备 read model 治理的核心边界：`ReadModelQueryGateway`、`ReadModelRefreshGateway`、`ReadModelScopePolicyRegistry`、`APP_STATUS_READ_MODEL_REGISTRY`、`RUNTIME_WORKER_REGISTRY` 和 operation freshness barrier。问题不在于完全没有统一入口，而在于 per-read-model manifest 还没有成为一个可审计的事实源：每个 key 的 owner、repository port、builder/worker、scope、source/schema contract、legacy path 和测试合同仍然分散在文档、registry、worker、route/service 和 `postgres_repositories/read_models.py` 中。

本轮建议的下一步不是直接拆文件，而是先把以下 manifest 条目固化成代码/测试事实源，再逐 key 迁移：

- read model key / scope type / refresh event / worker instance
- query owner 和 API/page owner
- refresh scope policy 和 force refresh 入口
- repository port / SQL owner / projection builder
- partition key / scope key / `all` scope 语义
- source version / schema version owner
- operation barrier target
- legacy read path / direct fresh path / direct queue write path
- 七类测试中的适用项和现有测试入口

## 当前共享边界

| 边界 | 当前入口 | 结论 |
| --- | --- | --- |
| Query freshness | `backend/src/fin_ops_platform/services/read_model_query_gateway.py` | 支持 expected source/schema、Redis fresh gate、payload validator、miss/stale enqueue；但仍有多个自管 freshness service 和 legacy route 需要 manifest 分类 |
| Refresh enqueue | `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py` | 非事务 refresh 统一 normalize/validate/dedupe 后写 durable queue |
| Scope policy | `backend/src/fin_ops_platform/services/read_model_scope_policy.py` | 14 个 App Status read model 已全部进入 registry；`pending_invoice` 和 `cost_statistics` 有特殊 policy，其余主要是 month/all |
| App Status registry | `backend/src/fin_ops_platform/services/app_status_read_model_registry.py` | 14 个 key 是当前 read model manifest 的最小集合 |
| Worker registry | `backend/src/fin_ops_platform/services/runtime_worker_registry.py` | 已登记 worker/read model/event/env/RabbitMQ eligibility；存在组合 worker 和多实例 worker，manifest 需要明确 primary owner 与辅助实例 |
| Operation barrier | `backend/src/fin_ops_platform/services/operation_freshness_barrier.py` | 通过 read model key/scope/type 读取 runtime snapshot，不写 readiness，不替代页面 fresh gate |
| SQL repository | `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` | 约 11329 行、385 个 symbol，承载多个 read model 的 query/save/mark 方法；是后续 repository port 拆分的主要风险点 |

## Read Model Manifest 库存

| Key | Scope policy | Refresh event | Worker owner | Query/read owner | SQL repository owner | Strategy | Permission owner | 测试入口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `workbench` | month/all；`all` query 必须有 active aggregate proof | `workbench.read_model.refresh` | `workbench`；另有 `workbench-matching` 维护 matching dirty scopes | `WorkbenchQueryFacade`、`/api/workbench*` legacy route | `get_workbench_view`、`get_workbench_groups_page`、`get_workbench_group_detail`、`save_workbench_read_models` | active generation + scoped publish；不能改成普通 full rebuild | Workbench API/session | `tests/test_workbench_sql_runtime.py`、`tests/test_workbench_query_facade.py`、`tests/test_read_model_architecture_guards.py` |
| `workbench_relation` | month/all fan-out；页面依赖按 month proof | `workbench_relation.read_model.refresh` | `workbench-relation` | `WorkbenchRelationReadFacade` 及下游页面 | `save_workbench_relation_distribution`、`list_workbench_relation_rows`、`get_workbench_relation_groups_by_ids` | scoped incremental distribution | 各下游 API/page | `tests/test_workbench_relation_read_facade.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |
| `bank_detail` | month/all；`all` 是 fan-out command，不是 queryable proof | `bank_detail.read_model.refresh` | `bank-detail` | `BankDetailsApplicationService`、bank details routes | `list_bank_detail_transactions`、`save_bank_detail_rows`、`mark_bank_detail_scope` | partitioned scoped + auto-tag source version | Bank details API/session | `tests/test_bank_details_sql_runtime.py`、`tests/test_bank_auto_tag_rules_api.py` |
| `bank_account_balance` | month/all | `bank_account_balance.read_model.refresh` | `bank-account-balance` | bank details balance endpoints | `list_bank_account_balances`、`save_bank_account_balances` | partitioned scoped account/month balance | Bank details API/session | `tests/test_bank_details_sql_runtime.py`、runtime worker registry tests |
| `pending_invoice` | special: `expense|income:<filter>[:YYYY-MM]`；裸 `all` 已禁止 | `pending_invoice.read_model.refresh` | `pending-invoice`，也可由 `search-pending` 组合 worker处理 | `PendingInvoiceReadModelService`、`routes_pending_invoices.py` | `list_pending_invoice_rows`、`list_pending_invoice_filter_options`、`save_pending_invoice_rows`、`mark_pending_invoice_scope` | scoped incremental list/detail/filter options | Pending invoices API/session | `tests/test_pending_invoice_service.py`、`tests/test_search_pending_sql_runtime.py` |
| `search` | month/all | `search.read_model.refresh` | `search`、`search-secondary`、`search-tertiary`，组合 worker `search-pending` | search API / pending search projection | `save_search_index_rows` plus `SearchPendingSqlProjectionBuilder` | partitioned scoped index | Search API/session | `tests/test_search_pending_sql_runtime.py`、worker registry tests |
| `invoice_lifecycle` | month/all | `invoice_lifecycle.read_model.refresh` | `invoice-lifecycle`、`invoice-lifecycle-secondary` | `InvoiceLifecycleReadFacade` 和相关页面 | `save_invoice_lifecycle_rows`、`mark_invoice_lifecycle_scope`、`list_invoice_lifecycle_rows` | scoped incremental with batch save | Invoice lifecycle pages/API | `tests/test_invoice_lifecycle_read_model_refresh.py`、`tests/test_postgres_repositories_boundaries.py` |
| `input_invoice_usage` | month/all | `input_invoice_usage.read_model.refresh` | `invoice-usage-collection` | input invoice usage read/detail/export services | `list_input_invoice_usage_rows`、`save_input_invoice_usage_rows`、`mark_input_invoice_usage_scope` | scoped incremental downstream of relation distribution | Input invoice usage API/session | `tests/test_input_invoice_usage_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` |
| `output_invoice_collection` | month/all | `output_invoice_collection.read_model.refresh` | `invoice-usage-collection` | output invoice collection services/routes | `list_output_invoice_collection_rows`、`save_output_invoice_collection_rows`、`mark_output_invoice_collection_scope` | scoped incremental downstream of relation distribution | Output invoice collection API/session | `tests/test_output_invoice_collection_api.py`、`tests/test_output_invoice_collection_service.py` |
| `oa_pending_payment` | month/all | `oa_pending_payment.read_model.refresh` | `invoice-usage-collection` | `OaPendingPaymentReadModelService`、routes | `list_oa_pending_payment_rows`、`save_oa_pending_payment_rows`、`mark_oa_pending_payment_scope` | scoped incremental downstream of OA/relation facts | OA pending payment API/session | `tests/test_oa_pending_payment_api.py`、`tests/test_oa_pending_payment_command_service.py` |
| `cost_statistics` | special: project/month/all normalized by runtime service | `cost_statistics.read_model.refresh` | `cost-statistics`；组合 worker `cost-tax` | `CostStatisticsQueryService` / cost routes | `get_cost_statistics_view`、`save_cost_statistics_read_models` | partitioned scoped rollup | Cost statistics API/session | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_scope_contract.py` |
| `tax_offset` | month/all | `tax_offset.read_model.refresh` | `tax-offset`；组合 worker `cost-tax` | `TaxOffsetQueryService` / tax routes | `get_tax_offset_view`、`save_tax_offset_read_models` | partitioned scoped tax month | Tax API/session | `tests/test_tax_offset_*`、`tests/test_read_model_refresh_gateway.py` |
| `no_oa_bank_batch` | month/all | `no_oa_bank_batch.read_model.refresh` | `no-oa-bank-batch` | `NoOaBankBatchApplicationService`、routes | `list_no_oa_bank_batch_rows` and refresh service | scoped incremental | No-OA bank batch API/session | `tests/test_no_oa_bank_batch_*` |
| `turnover_ledger` | month/all | `turnover_ledger.read_model.refresh` | `turnover-ledger` | `TurnoverLedgerQueryService`、routes/write adapters | `list_turnover_ledger_view`、`save_turnover_ledger_rows` | partitioned scoped ledger | Turnover ledger API/session | `tests/test_turnover_ledger_*` |

## IO 合同模板应用

每个 manifest 条目后续必须填写以下字段，不能只登记 key：

| 字段 | 必填内容 |
| --- | --- |
| Input | API query params、scope key、filter/page/sort、expected source/schema、上游写入 affected scopes |
| Output | payload shape、`read_model_status`、`refresh_enqueued`、`read_model_stale_reasons`、source/schema versions、operation barrier targets |
| State | fresh / refreshing / stale / missing / failed / unavailable / schema mismatch / source mismatch |
| Event | refresh event、dirty scope reason、outbox metadata.action_name、readiness publish、worker heartbeat |
| Read model | repository port、projection builder、worker handler、partition key、full rebuild fallback |
| Permission | 具体 route/service/session owner；read model 边界不得自行放宽权限 |
| Test contract | gateway、service、API、worker/readiness、frontend stale/empty、cross-page regression、legacy contamination guard |
| Legacy contract | 删除、隔离或 compat-only；保留时必须有 owner、调用者、删除条件和 guard |

## 当前缺口和风险

| ID | 缺口 | 风险 | 后续边界 |
| --- | --- | --- | --- |
| RM-GAP-001 | manifest 还不是代码事实源 | 新增 read model 可能只改 app status 或 worker registry 的其中一处 | `read-models:query-gateway-contract-and-status-parity` 前新增 manifest/parity guard |
| RM-GAP-002 | `read_models.py` 聚合了多个 read model 的 query/save/mark | 后续小改容易跨 key 误伤，repository owner 不清 | `read-models:repository-port-and-sql-owner-split-plan` |
| RM-GAP-003 | 仍有自管 freshness/direct fresh 路径 | 可能绕过 `ReadModelQueryGateway` 或缺少 expected contract | `read-models:query-gateway-contract-and-status-parity` |
| RM-GAP-004 | `all` scope 语义依 key 不一致 | fan-out command 被误用成 query freshness proof | 每个 per-key contract 必须注明 `all` 是 command、aggregate proof 还是 forbidden |
| RM-GAP-005 | 组合 worker / 多实例 worker 的 primary owner 不明确 | manifest 若只记录一个 worker，会漏掉实际 deployment/registry parity | manifest 必须保留 primary owner + auxiliary instances |
| RM-GAP-006 | 事务内 producer 不一定显式映射到 scope policy registry | 可能直接写 legacy/invalid scope 到 durable queue | legacy removal guards 和 transaction producer tests |
| RM-GAP-007 | 权限 owner 分散在 route/page，read model 文档没有逐 key 指明 | 重构时可能把 read model service 误当可直接公开的 API | per-key module contract |

## 下一阶段建议

下一阶段应推进 `read-models:query-gateway-contract-and-status-parity`，但仍要保持小步：

1. 新增一个轻量 `ReadModelManifest` 或 manifest data module，先从现有 `APP_STATUS_READ_MODEL_REGISTRY`、`RUNTIME_WORKER_REGISTRY`、scope policy registry 派生并做 parity guard。
2. 不迁移业务行为，只让测试证明 14 个 key 都有 app status、worker、scope policy、event、repository owner、test owner。
3. 把 direct fresh / self-managed freshness call site 全部分类到 manifest：`query_gateway`、`equivalent_active_generation`、`legacy_compat_only`、`must_remove`。
4. 后续再按 key 拆 repository port；不要直接把 `read_models.py` 全量拆成一大波改动。

## 不做事项

- 不实现 Go/Fiber 或 Go Worker。
- 不执行生产 SSH/DB 操作。
- 不改 `ReadModelQueryGateway`、`ReadModelRefreshGateway` 或 SQL repository 行为。
- 不把 Workbench active generation 改造成普通 read model rebuild。
- 不把 `all` scope 统一解释为 queryable fresh proof。

## 验收

- 已完成 14 个 App Status read model key 的 manifest 库存。
- 已记录每个 key 的 scope/event/worker/query/repository/strategy/permission/test owner。
- 已明确下一阶段要先做 manifest/parity guard，再做 query gateway parity 和 repository port split。
- 本轮没有行为改动；生产证据不适用，标记为 `not-required-for-analysis`。
