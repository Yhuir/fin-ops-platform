# PostgreSQL 目标数据设计

本文定义 app 数据迁移到 PostgreSQL 的目标边界。设计原则是先承接当前 Python 后端的业务事实，保持前端 API 兼容；后续再决定是否执行 Axum/API/Worker 全量重构。

## 总体目标

完成后系统形态：

```text
React 前端
  |
  v
Python fin-ops API
  |
  +-- PostgreSQL fin_ops：app 主业务事实、设置、任务、审计、read model
  |
  +-- OA Mongo form_data_db：只读读取 OA 源数据
  |
  +-- GridFS 或后续对象存储：迁移期文件读取，后续可独立迁 MinIO/S3
```

长期可演进为：

```text
React 前端 -> Axum API -> PostgreSQL + MinIO/S3 + worker
                         -> OA Mongo 只读同步器
```

第一版迁移不要求一次性替换 Python HTTP 服务。

## Schema 分层

建议在 `fin_ops` 单库中使用多 schema：

| Schema | 用途 |
| --- | --- |
| `app` | 核心业务事实和设置。 |
| `read_model` | 工作台、搜索、成本统计、税金抵扣等可重建投影。 |
| `job` | 后台任务、dirty scope、outbox、迁移任务状态。 |
| `audit` | 操作审计、迁移审计、对账报告摘要。 |
| `staging` | Mongo 导出导入中间表、原始 payload、旧 id 映射。 |

建议启用扩展：

```sql
create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists btree_gin;
```

## ID 和金额规则

- 新 PostgreSQL 主键使用 `uuid`。
- 所有从 Mongo 迁入对象保留旧 id：`legacy_mongo_id text`。
- 所有外部 OA 对象保留 OA 原始 id：`oa_source_id text`。
- 所有金额使用 `numeric(18, 2)` 或更高精度 `numeric(20, 6)`；禁止使用 float。
- 日期字段按业务含义拆分：
  - 业务日期：`date`
  - 时间戳：`timestamptz`
  - 月份 scope：`date`，固定为当月第一天。
- 删除优先软删除或状态流转，不物理删除业务事实。

## 核心表设计

### 导入与文件

目标表：

- `app.import_batches`
- `app.import_batch_rows`
- `app.import_files`
- `app.file_objects`
- `staging.mongo_import_batches`
- `staging.mongo_file_objects`

`app.import_batches` 建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `uuid primary key` | 新 id。 |
| `legacy_mongo_id` | `text unique` | Mongo `import_batches._id`。 |
| `batch_type` | `text not null` | 发票、流水、ETC 等。 |
| `source_name` | `text not null` | 来源文件或来源名称。 |
| `imported_by` | `text not null` | 导入人。 |
| `row_count` | `integer not null` | 总行数。 |
| `success_count` | `integer not null` | 成功行数。 |
| `error_count` | `integer not null` | 错误行数。 |
| `duplicate_count` | `integer not null default 0` | 重复数。 |
| `status` | `text not null` | 当前状态。 |
| `imported_at` | `timestamptz not null` | 导入时间。 |
| `raw_payload` | `jsonb not null default '{}'` | 迁移保留 payload。 |
| `created_at` | `timestamptz not null default now()` | 创建时间。 |
| `updated_at` | `timestamptz not null default now()` | 更新时间。 |

索引：

- `(batch_type, imported_at desc)`
- `(status, imported_at desc)`
- `unique(legacy_mongo_id)`

文件存储策略：

- 阶段一可保留 GridFS，并在 `app.file_objects.storage_backend='gridfs'` 保存 `gridfs://...`。
- 阶段二再迁 MinIO/S3，并将 `storage_backend` 改为 `s3`，保存 `bucket`、`object_key`、`sha256`、`size_bytes`。
- 文件迁移不要阻塞数据库事实迁移。

### 银行流水

目标表：

- `app.bank_transactions`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_events`

`app.bank_transactions` 建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `uuid primary key` | 新 id。 |
| `legacy_mongo_id` | `text unique` | Mongo `_id`。 |
| `account_no` | `text not null` | 账号。 |
| `account_name` | `text` | 户名。 |
| `txn_direction` | `text not null` | 借/贷方向。 |
| `counterparty_name_raw` | `text not null` | 对方名称。 |
| `normalized_counterparty_name` | `text` | 规范化名称。 |
| `amount` | `numeric(18,2) not null` | 绝对金额。 |
| `signed_amount` | `numeric(18,2) not null` | 带方向金额。 |
| `written_off_amount` | `numeric(18,2) not null default 0` | 已核销金额。 |
| `txn_date` | `date` | 交易日期。 |
| `txn_month` | `date` | 月份 scope。 |
| `trade_time` | `timestamptz` | 交易时间。 |
| `bank_serial_no` | `text` | 银行流水号。 |
| `source_unique_key` | `text` | 来源唯一键。 |
| `data_fingerprint` | `text` | 数据指纹。 |
| `source_batch_id` | `uuid references app.import_batches(id)` | 来源批次。 |
| `status` | `text not null` | 状态。 |
| `raw_payload` | `jsonb not null default '{}'` | 原始/扩展字段。 |

索引：

- `(txn_month, account_no, txn_date)`
- `(txn_month, txn_direction, amount)`
- `(txn_month, counterparty_name_raw)`
- `(source_batch_id)`
- `gin(counterparty_name_raw gin_trgm_ops)`
- `unique(source_unique_key)` where not null
- `unique(data_fingerprint)` where not null

数据量超过百万后，再按 `txn_month` 月分区；当前生产仅 431 条，不需要第一阶段引入复杂分区。

### 发票

目标表：

- `app.invoices`
- `app.invoice_inventory_events`
- `app.invoice_certifications`

`app.invoices` 建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `uuid primary key` | 新 id。 |
| `legacy_mongo_id` | `text unique` | Mongo `_id`。 |
| `invoice_type` | `text not null` | 发票类型。 |
| `invoice_no` | `text not null` | 发票号码。 |
| `invoice_code` | `text` | 发票代码。 |
| `digital_invoice_no` | `text` | 数电票号码。 |
| `invoice_date` | `date` | 开票日期。 |
| `invoice_month` | `date` | 月份 scope。 |
| `counterparty_id` | `text` | 当前模型内 counterparty id。 |
| `counterparty_name` | `text` | 当前模型内 counterparty name。 |
| `seller_name` | `text` | 销方。 |
| `seller_tax_no` | `text` | 销方税号。 |
| `buyer_name` | `text` | 购方。 |
| `buyer_tax_no` | `text` | 购方税号。 |
| `amount` | `numeric(18,2) not null` | 不含税或业务金额，按现有语义迁移。 |
| `tax_amount` | `numeric(18,2)` | 税额。 |
| `total_with_tax` | `numeric(18,2)` | 价税合计。 |
| `signed_amount` | `numeric(18,2) not null` | 带方向金额。 |
| `written_off_amount` | `numeric(18,2) not null default 0` | 已核销金额。 |
| `source_batch_id` | `uuid references app.import_batches(id)` | 来源批次。 |
| `oa_form_id` | `text` | 来源 OA form。 |
| `etc_invoice_id` | `text` | ETC 发票 id。 |
| `workbench_visibility` | `text not null default 'visible'` | 工作台可见性。 |
| `status` | `text not null` | 状态。 |
| `raw_payload` | `jsonb not null default '{}'` | 扩展字段。 |

索引：

- `(invoice_month, invoice_no)`
- `(invoice_month, buyer_name)`
- `(invoice_month, seller_name)`
- `(invoice_month, total_with_tax)`
- `(invoice_type, status)`
- `gin(invoice_no gin_trgm_ops)`
- `gin(buyer_name gin_trgm_ops)`
- `gin(seller_name gin_trgm_ops)`
- `unique(source_unique_key)` where not null
- `unique(data_fingerprint)` where not null

### 工作台关系、异常和覆盖

目标表：

- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.workbench_exception_case_events`
- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`

第一阶段建议保留 `workbench_pair_relations` 与现有服务概念一致，避免一次性拆成过细的核销 case 模型。后续可演进为：

- `app.reconciliation_cases`
- `app.reconciliation_case_rows`
- `app.reconciliation_case_events`

`app.workbench_pair_relations` 建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `uuid primary key` | 新 id。 |
| `legacy_mongo_id` | `text unique` | Mongo `_id`。 |
| `case_id` | `text not null unique` | 现有 case id。 |
| `status` | `text not null` | active/reverted/cancelled 等。 |
| `relation_mode` | `text not null` | 关系类型。 |
| `month_scope` | `date` | 月份 scope。 |
| `row_ids` | `text[] not null` | 现有 row ids。 |
| `row_types` | `text[] not null` | OA/bank/invoice。 |
| `note` | `text` | 备注。 |
| `amount_check` | `jsonb not null default '{}'` | 金额检查结果。 |
| `special_metadata` | `jsonb not null default '{}'` | 特殊规则元数据。 |
| `created_by` | `text` | 创建人。 |
| `created_at` | `timestamptz not null` | 创建时间。 |
| `updated_at` | `timestamptz not null` | 更新时间。 |
| `raw_payload` | `jsonb not null default '{}'` | 原始 payload。 |

索引：

- `(status, month_scope)`
- `gin(row_ids)`
- `(relation_mode, status)`
- `unique(case_id)`

约束：

- 同一 row 在 active 关系中的重复绑定必须按现有业务规则判定，不可简单允许重复。
- 撤回不物理删除，必须保留 history/event。

### OA 只读投影

目标表：

- `app.oa_sync_runs`
- `app.oa_sync_watermarks`
- `app.oa_applications`
- `app.oa_application_items`
- `app.oa_attachments`

注意：这些表是 app 自己的 OA 投影，不是 OA 事实源。OA 源仍为 Mongo `form_data_db.form_data`。

`app.oa_applications` 建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `uuid primary key` | app 投影 id。 |
| `oa_source_id` | `text not null` | Mongo `_id`。 |
| `form_id` | `text not null` | OA form id。 |
| `form_type` | `text not null` | payment_request / expense_claim / project。 |
| `row_id` | `text not null unique` | 当前工作台 row id。 |
| `workflow_no` | `text` | 流程编号。 |
| `status` | `text` | 归一化流程状态。 |
| `applicant` | `text` | 申请人。 |
| `application_date` | `date` | 申请日期。 |
| `approved_at` | `timestamptz` | 审批完成时间。 |
| `project_id` | `text` | 项目 id。 |
| `project_name` | `text` | 项目名。 |
| `amount` | `numeric(18,2)` | 总金额。 |
| `source_updated_at` | `timestamptz` | OA 源更新时间。 |
| `normalized_payload` | `jsonb not null default '{}'` | 常用字段归一化。 |
| `raw_payload` | `jsonb not null default '{}'` | 原始摘要。 |

索引：

- `unique(oa_source_id, form_id)`
- `(form_type, status, application_date)`
- `(project_name)`
- `gin(project_name gin_trgm_ops)`
- `gin(applicant gin_trgm_ops)`
- `gin(normalized_payload)`

只读规则：

- 同步器只读 Mongo，不写 OA Mongo。
- 同步任务必须支持从水位重放。
- 页面可优先读取 `app.oa_applications`，但必须能 fallback 到 `MongoOAAdapter` 或显示同步滞后。

### 税金和 ETC

目标表：

- `app.tax_certified_import_sessions`
- `app.tax_certified_import_batches`
- `app.tax_certified_import_records`
- `app.etc_import_batches`
- `app.etc_invoices`
- `app.etc_business_batches`
- `app.etc_reconciliation_tasks`
- `app.etc_reconciliation_files`
- `app.historical_etc_repair_bundles`
- `app.historical_etc_repair_parsed_seeds`
- `app.historical_etc_repair_states`

第一阶段可以把复杂 ETC task snapshot 先保存在结构化主字段 + `raw_payload jsonb`，再逐步拆细。不能把业务关键状态只留在无法查询的 JSONB 中：

- task id
- status
- owner
- linked import batch ids
- linked OA row id
- invoice count
- total amount
- updated_at

这些字段必须拆列。

### 设置、任务、健康

目标表：

- `app.app_settings`
- `job.background_jobs`
- `audit.app_health_alerts`
- `job.workbench_matching_dirty_scopes`
- `job.outbox_events`

`job.outbox_events` 建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `uuid primary key` | 事件 id。 |
| `aggregate_type` | `text not null` | 聚合类型。 |
| `aggregate_id` | `text not null` | 聚合 id。 |
| `event_type` | `text not null` | 事件类型。 |
| `payload` | `jsonb not null default '{}'` | 事件内容。 |
| `status` | `text not null default 'pending'` | pending/published/failed。 |
| `available_at` | `timestamptz not null default now()` | 可投递时间。 |
| `published_at` | `timestamptz` | 投递时间。 |
| `attempt_count` | `integer not null default 0` | 尝试次数。 |
| `last_error` | `text` | 最近错误。 |
| `created_at` | `timestamptz not null default now()` | 创建时间。 |

业务写操作和 outbox 必须同事务提交。

## Read model 设计

### 工作台

目标表：

- `read_model.workbench_rows`
- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`

`read_model.workbench_rows` 建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `uuid primary key` | 投影 id。 |
| `scope_month` | `date not null` | 月份。 |
| `row_id` | `text not null` | 现有 row id。 |
| `row_type` | `text not null` | oa/bank/invoice。 |
| `source_kind` | `text not null` | 来源。 |
| `business_date` | `date` | 业务日期。 |
| `counterparty_name` | `text` | 对方。 |
| `project_name` | `text` | 项目。 |
| `amount` | `numeric(18,2)` | 金额。 |
| `status` | `text` | 展示状态。 |
| `group_key` | `text` | 分组 key。 |
| `relation_case_id` | `text` | 关联 case。 |
| `candidate_match_id` | `text` | 候选 id。 |
| `exception_case_id` | `text` | 异常 case。 |
| `source_versions` | `jsonb not null default '{}'` | 版本。 |
| `payload` | `jsonb not null default '{}'` | 展示 payload。 |
| `updated_at` | `timestamptz not null default now()` | 更新时间。 |

索引：

- `unique(scope_month, row_id)`
- `(scope_month, row_type, status)`
- `(scope_month, relation_case_id)`
- `(scope_month, exception_case_id)`
- `gin(counterparty_name gin_trgm_ops)`
- `gin(project_name gin_trgm_ops)`
- `gin(payload)`

### 搜索

目标表：

- `read_model.search_index_rows`

核心索引：

- `(scope_month, entity_type)`
- `gin(searchable_text gin_trgm_ops)`
- `(entity_type, entity_id)`

全局搜索 API 第一阶段只查这张表，禁止每次请求跨 OA、流水、发票、关系表实时拼全量。

## Mongo 到 PostgreSQL 映射

| Mongo / 当前状态 | PostgreSQL 目标 | 迁移策略 |
| --- | --- | --- |
| `import_batches` | `app.import_batches`、`app.import_batch_rows` | 复用 `ImportNormalizationService` 或 `ApplicationStateStore` 导出。 |
| `invoices` | `app.invoices` | 金额、日期、counterparty 拆列，保留 raw_payload。 |
| `bank_transactions` | `app.bank_transactions` | 金额、方向、账户、日期拆列。 |
| `file_import_sessions` | `app.import_batches`、`app.import_files` | 迁移导入会话和文件状态。 |
| `file_import_files` | `app.import_files`、`app.file_objects` | 记录 GridFS path，后续迁对象存储。 |
| GridFS | `app.file_objects` | 第一阶段保留 GridFS，第二阶段迁 S3/MinIO。 |
| `workbench_row_overrides` | `app.workbench_row_overrides` | 行覆盖拆列 + payload。 |
| `workbench_exception_cases` | `app.workbench_exception_cases`、events | 保留状态和 row index。 |
| `workbench_pair_relations` | `app.workbench_pair_relations`、history | 保留 case_id、row_ids、状态和金额检查。 |
| `workbench_read_models` | `read_model.workbench_rows`、`workbench_snapshots` | 优先重建，不强制逐字节迁移。 |
| `workbench_candidate_matches` | `read_model.workbench_candidate_matches` | 候选 key、scope、状态拆列。 |
| `workbench_matching_dirty_scopes` | `job.workbench_matching_dirty_scopes`、`job.outbox_events` | 迁移为任务/事件。 |
| `no_oa_bank_batches` | `app.no_oa_bank_batches` | 保留批次、row_ids、status、version。 |
| `no_oa_bank_batch_audit_log` | `app.no_oa_bank_batch_events` 或 `audit.events` | 审计事件。 |
| `turnover_relations` | `app.turnover_relations` | 往来关系事实。 |
| `turnover_relation_audit_log` | `audit.events` | 审计事件。 |
| `turnover_ledger_extras` | `app.turnover_ledger_extras` | 台账补充字段。 |
| `cost_statistics_read_models` | `read_model.cost_statistics_read_models` | 可重建，先迁缓存再建立重建器。 |
| `tax_offset_read_models` | `read_model.tax_offset_read_models` | 可重建。 |
| `oa_attachment_invoice_cache` | `app.oa_attachment_invoice_cache` 或 `read_model.oa_attachment_invoice_cache` | 缓存，可保留 TTL 和 parser version。 |
| `oa_sync_state` | `app.oa_sync_watermarks`、`job.oa_sync_runs` | 水位和同步状态。 |
| `manual_oa_imports` | `app.manual_oa_imports`、events | 手工导入状态和审计。 |
| `app_settings` | `app.app_settings` | 设置拆列 + JSONB。 |
| `tax_certified_import_*` | `app.tax_certified_import_*` | 已认证发票导入。 |
| `etc_state` | `app.etc_*` | 逐步拆结构化表，保留 raw_payload。 |
| `etc_reconciliation_state` | `app.etc_reconciliation_*` | task 主字段拆列，复杂 payload 保留 JSONB。 |
| `historical_etc_repair_*` | `app.historical_etc_repair_*` | 保留修复包和解析结果。 |
| `background_jobs` | `job.background_jobs` | 任务状态。 |
| `app_health_alerts` | `audit.app_health_alerts` | 告警状态。 |

## 切换策略

应用配置建议：

```text
FIN_OPS_APP_STORAGE_BACKEND=mongo|postgres|dual
FIN_OPS_APP_READ_BACKEND=mongo|postgres|shadow
DATABASE_URL=<postgres-dsn-from-secret-manager>
```

阶段含义：

- `mongo`：保持当前行为。
- `postgres`：读写 PostgreSQL。
- `dual`：写 Mongo + PostgreSQL，读按 `FIN_OPS_APP_READ_BACKEND` 决定。
- `shadow`：用户仍看 Mongo 结果，同时后台执行 PostgreSQL 查询并记录差异。

迁移完成条件：

- app 写路径全部进入 PostgreSQL。
- 用户读路径全部来自 PostgreSQL 或 PostgreSQL read model。
- OA 源数据仍从 OA Mongo 只读读取，或从只读同步投影读取。
- app Mongo 冻结归档，不再承载生产写入。
