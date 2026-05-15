# PostgreSQL 数据模型、分区和读模型计划

## 设计原则

- PostgreSQL 是核心业务事实源。
- Mongo app 数据只作为迁移来源和回滚参考。
- OA Mongo 只读，同步后进入 PostgreSQL 归一化表。
- 所有财务金额使用 `numeric`，不得使用 float。
- 高频查询必须有明确索引和 `EXPLAIN ANALYZE` 验证。
- 页面读模型可以冗余，但必须能从事实表重建。
- 所有写操作都要留下审计事件和 outbox 事件。

## Schema 分层

建议使用单库多 schema：

| Schema | 用途 |
| --- | --- |
| `app` | 核心业务事实表。 |
| `read_model` | 工作台、搜索、统计等物化读模型。 |
| `job` | outbox、任务状态、worker 心跳。 |
| `audit` | 审计日志和变更历史。 |
| `staging` | 导入解析、Mongo 迁移、OA 同步中间结果。 |

## 核心事实表

### 导入和文件

- `app.import_batches`
- `app.import_files`
- `app.file_objects`
- `staging.import_parse_results`
- `staging.import_parse_issues`

关键字段：

- `id`
- `source_type`
- `status`
- `idempotency_key`
- `checksum`
- `created_by`
- `created_at`
- `confirmed_at`
- `reverted_at`

### 银行流水

- `app.bank_transactions`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_events`

建议按 `txn_month` 或 `txn_date` 分区。

核心索引：

- `(txn_month, account_no, txn_date)`
- `(txn_month, counterparty_name)`
- `(txn_month, amount)`
- `(source_batch_id)`
- `gin(counterparty_name gin_trgm_ops)`，用于模糊搜索。

### 发票

- `app.invoices`
- `app.invoice_certifications`
- `app.invoice_inventory_events`

建议按 `invoice_month` 或 `issued_at` 分区。

核心索引：

- `(invoice_month, invoice_no)`
- `(invoice_month, buyer_name)`
- `(invoice_month, seller_name)`
- `(invoice_month, total_amount)`
- `(invoice_type, status)`
- `gin(invoice_no gin_trgm_ops)`
- `gin(buyer_name gin_trgm_ops)`
- `gin(seller_name gin_trgm_ops)`

### OA 归一化

- `app.oa_applications`
- `app.oa_application_items`
- `app.oa_attachments`
- `app.oa_sync_runs`
- `app.oa_sync_watermarks`

OA 原始 Mongo `_id`、流程编号和表单类型必须保留，用于追溯：

- `oa_source_id`
- `form_type`
- `workflow_no`
- `status`
- `applicant`
- `project_id`
- `project_name`
- `approved_at`
- `source_updated_at`
- `normalized_payload`

`normalized_payload` 可以用 `jsonb` 保留不常用字段，但常用筛选字段必须拆列。

### 核销和异常

- `app.reconciliation_cases`
- `app.reconciliation_case_rows`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.no_oa_bank_batches`
- `app.turnover_relations`

关键约束：

- 同一个有效 case 的 row 不能重复绑定到另一个 active case，除非业务允许多关系。
- 撤回不物理删除，使用状态流转。
- 所有确认、撤销、异常处理必须写 `audit.events`。

### 后台任务和 outbox

- `job.outbox_events`
- `job.worker_tasks`
- `job.worker_attempts`
- `job.dead_letters`

`outbox_events` 建议字段：

- `id`
- `aggregate_type`
- `aggregate_id`
- `event_type`
- `payload`
- `status`
- `available_at`
- `published_at`
- `attempt_count`
- `last_error`
- `created_at`

业务写操作和 outbox 写入必须在同一个 PostgreSQL 事务里提交。

## 分区策略

建议第一阶段只对大表分区：

- `app.bank_transactions`
- `app.invoices`
- `app.oa_applications`
- `read_model.workbench_rows`
- `read_model.search_index_rows`

分区粒度：

- 最近两年数据量高时按月。
- 数据量中等时按年。
- 迁移初期无法确认规模时先按月设计，压测后决定是否合并。

示例：

```sql
create table app.bank_transactions (
  id uuid primary key,
  txn_date date not null,
  txn_month date not null,
  account_no text not null,
  counterparty_name text,
  amount numeric(18, 2) not null,
  direction text not null,
  source_batch_id uuid not null,
  created_at timestamptz not null default now()
) partition by range (txn_month);

create table app.bank_transactions_2026_05
  partition of app.bank_transactions
  for values from ('2026-05-01') to ('2026-06-01');
```

生产中必须自动创建未来分区，并对缺失分区告警。

## 搜索表

不要在页面请求中跨多张事实表做模糊搜索。建立统一搜索表：

```sql
create table read_model.search_index_rows (
  id uuid primary key,
  entity_type text not null,
  entity_id uuid not null,
  scope_month date,
  title text not null,
  subtitle text,
  searchable_text text not null,
  amount numeric(18, 2),
  status text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index search_index_rows_scope_idx
  on read_model.search_index_rows (scope_month, entity_type);

create index search_index_rows_text_trgm_idx
  on read_model.search_index_rows
  using gin (searchable_text gin_trgm_ops);
```

`search_index_rows` 由事实变更触发异步更新。全局搜索 API 只查这张表或少数补充表。

## 工作台读模型

建议拆两层：

- `read_model.workbench_rows`：行级投影，支持分页、筛选、搜索、定位。
- `read_model.workbench_snapshots`：页面级快照，支持快速返回固定口径。

行级投影字段：

- `scope_month`
- `row_id`
- `row_type`
- `source_kind`
- `business_date`
- `counterparty_name`
- `project_name`
- `amount`
- `status`
- `group_key`
- `relation_case_id`
- `candidate_match_id`
- `exception_case_id`
- `payload`
- `source_versions`

重建策略：

- 导入确认：重建对应月份。
- OA 同步：重建受影响 OA 单据月份。
- 关系确认/撤销：重建相关 row 所在月份。
- 异常处理：重建异常涉及月份。
- 分类变更：重建流水所在月份和统计 read model。
- all-time 汇总：后台增量聚合，不阻塞单月读。

## Mongo 到 PostgreSQL 映射

| 当前 Mongo/服务状态 | PostgreSQL 目标 |
| --- | --- |
| `import_batches` | `app.import_batches` |
| `invoices` | `app.invoices` |
| `bank_transactions` | `app.bank_transactions` |
| `file_import_sessions` | `app.import_batches`、`app.import_files` |
| `file_import_files` | `app.file_objects`、`app.import_files` |
| GridFS 文件 | MinIO/S3 对象 + `app.file_objects` |
| `workbench_row_overrides` | `app.workbench_row_overrides` |
| `workbench_pair_relations` | `app.reconciliation_cases`、`app.reconciliation_case_rows` |
| `workbench_read_models` | `read_model.workbench_rows`、`read_model.workbench_snapshots` |
| `workbench_candidate_matches` | `read_model.workbench_candidate_matches` |
| `workbench_matching_dirty_scopes` | `job.worker_tasks` 或 `job.outbox_events` |
| `background_jobs` | `job.worker_tasks`、`job.worker_attempts` |
| `app_health_alerts` | `audit.events` 或运维告警表 |

当前 Mongo 中部分 payload 是 Python pickle 或 GridFS 二进制。迁移工具不应手写 BSON/pickle 解析逻辑，优先复用现有 Python `ApplicationStateStore` 和业务 service 读取快照，再导出规范化 JSON/NDJSON 给 PostgreSQL 导入。

## 索引验收

每个核心 API 上线前必须保留：

- 查询 SQL。
- 参数规模。
- `EXPLAIN ANALYZE` 输出。
- P95/P99 目标。
- 是否命中索引。
- 是否触发全表扫描。

慢查询修复优先级：

1. 查询条件是否能定位分区。
2. 是否缺少组合索引。
3. 是否把 JSONB 当主查询字段。
4. 是否在请求路径实时聚合大表。
5. 是否应改为 read model 或后台任务。

