# Read Model Repository Port And SQL Owner Split Plan

**日期:** 2026-06-23
**Boundary:** `read-models:repository-port-and-sql-owner-split-plan`
**状态:** `closed-autonomous`
**范围:** repository owner map / port contract guard；不拆分 `read_models.py`，不改变 SQL、API、worker runtime、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮使用 CodeGraph 和结构搜索审阅了 `PostgresReadModelRepository`、页面 query facade/service 调用点和 `postgres_repositories/read_models.py` 中各 read model 方法。结论是：

- `read_models.py` 仍是 read model SQL 的最大耦合中心，包含 query、save、mark scope、active generation、source version、matching dirty queue 等多种职责。
- 当前业务服务多数通过 duck-typed `getattr(repository, "...")` 消费 read model rows；因此直接拆文件风险高，应该先把 per-read-model repository port 合同固定下来。
- 本轮不做大规模拆分，只把每个 manifest read model 的 `repository_port_contract` 登记到代码级 manifest，并加测试确认这些方法真实存在且只有一个 read model owner。

这使后续拆 `read_models.py` 时有可执行 owner map：每迁移一个 key，只需要迁移该 key 的 port contract 方法，并保持 manifest/tests 通过。

## Repository Owner Map

| Read model | Repository port contract |
| --- | --- |
| `workbench` | `get_workbench_view`, `get_workbench_summary`, `get_workbench_groups_page`, `get_workbench_group_detail`, `get_workbench_row_detail`, `get_workbench_refresh_status`, `get_workbench_groups_freshness_status`, `save_workbench_read_models`, `load_workbench_read_models` |
| `workbench_relation` | `save_workbench_relation_distribution`, `mark_workbench_relation_scope_empty`, `get_workbench_relation_rows_by_ids`, `list_workbench_relation_rows`, `get_workbench_relation_groups_by_ids`, `workbench_relation_source_versions` |
| `bank_detail` | `bank_detail_scope_keys_for_range`, `bank_detail_scope_summary`, `list_bank_detail_transactions`, `list_bank_detail_accounts`, `get_bank_detail_tagged_rows_by_transaction_ids`, `list_bank_detail_tagged_rows_by_month`, `save_bank_detail_rows`, `mark_bank_detail_scope` |
| `bank_account_balance` | `bank_account_balance_scope_summary`, `list_bank_account_balances`, `save_bank_account_balances` |
| `pending_invoice` | `list_pending_invoice_rows`, `list_pending_invoice_filter_options`, `save_pending_invoice_rows`, `mark_pending_invoice_scope`, `pending_invoice_source_summary`, `pending_invoice_bank_detail_source_versions`, `pending_invoice_workbench_relation_source_versions` |
| `search` | `search_index`, `save_search_index_rows` |
| `invoice_lifecycle` | `save_invoice_lifecycle_rows`, `mark_invoice_lifecycle_scope`, `get_invoice_lifecycle_rows_by_subject_ids`, `get_invoice_lifecycle_rows_by_identity_keys`, `list_invoice_lifecycle_rows` |
| `input_invoice_usage` | `list_input_invoice_usage_rows`, `save_input_invoice_usage_rows`, `mark_input_invoice_usage_scope`, `prune_input_invoice_usage_scope_shards`, `get_input_invoice_usage_row_by_row_id` |
| `output_invoice_collection` | `list_output_invoice_collection_rows`, `save_output_invoice_collection_rows`, `mark_output_invoice_collection_scope`, `prune_output_invoice_collection_scope_shards` |
| `oa_pending_payment` | `list_oa_pending_payment_rows`, `save_oa_pending_payment_rows`, `mark_oa_pending_payment_scope`, `prune_oa_pending_payment_scope_shards`, `get_oa_pending_payment_row_by_row_id`, `get_oa_pending_payment_row_by_oa_id`, `get_oa_pending_payment_row_by_bank_transaction_id`, `get_oa_pending_payment_row_by_invoice_id` |
| `cost_statistics` | `load_cost_statistics_read_models`, `get_cost_statistics_view`, `save_cost_statistics_read_models` |
| `tax_offset` | `load_tax_offset_read_models`, `get_tax_offset_view`, `save_tax_offset_read_models` |
| `no_oa_bank_batch` | `list_no_oa_bank_batch_rows` |
| `turnover_ledger` | `list_turnover_ledger_view`, `save_turnover_ledger_rows`, `clear_turnover_ledger_rows` |

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 模块类型: 共享边界 / 资源模块
- 本次改动类型: repository owner inventory / port contract guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否拆分 `read_models.py`: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. Legacy 退役与污染防护

| Legacy path | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| `read_models.py` 超大共享 repository | 多 read model 方法共处一个类 | 建立 per-key port contract owner map | 后续按 key/port 小步迁移 |
| duck-typed repository method 调用 | query service/facade 多处 `getattr(...)` | 先登记合法 method owner | 后续把关键 service 构造函数改为明确 port |
| live scan / legacy fallback | 仍散布在部分业务模块 | 本轮只识别风险，不改变行为 | page-specific boundary 删除或隔离 |
| shared helper/private methods | 仍在 `read_models.py` 内部共享 | 本轮不拆，避免触发大范围行为变化 | 拆分时保留 platform helper |

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改业务规则 |
| 2. Service-layer tests | 适用 | manifest repository port contract 方法存在且单 owner |
| 3. API contract tests | 不适用 | 无 HTTP/API shape 变化 |
| 4. Read model/cache/background job tests | 适用 | read model repository port owner map 进入 manifest guard |
| 5. Frontend component and interaction tests | 不适用 | 无前端变化 |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不跨业务写链路 |
| 7. Existing feature regression tests | 适用 | manifest、runtime worker、architecture guard 组合保持通过 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是代码/contract guard。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- Secret handling: 未读取、未记录 secret。

## 后续边界

下一步推进 `read-models:workbench-active-generation-contract`：

- Workbench 是 special read model，保留 active generation 原子发布，不机械套普通 gateway。
- 先锁定 active generation、summary、groups page、group detail、row detail 和 refresh status 的 owner/test contract。
- 不改 worker rebuild、不改 matching、不做 Go/Fiber。
