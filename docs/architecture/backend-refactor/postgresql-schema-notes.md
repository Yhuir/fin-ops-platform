# PostgreSQL Schema 详细设计

本文是后端重构中 PostgreSQL schema 与 SQLx migration 的设计说明。当前任务只输出设计文档，不创建 migration 文件，不连接 PostgreSQL 服务，不访问 OA 源数据库。

## 设计边界

- PostgreSQL 是财务核心事实源，Mongo app 数据只作为迁移来源和回滚对账参考。
- OA Mongo 保持只读，仅由同步任务读取，归一化结果写入 PostgreSQL。
- 文件内容进入 MinIO/S3，PostgreSQL 只保存对象元数据、校验值、来源关系和审计线索。
- 页面查询优先走 `read_model`，读模型可以冗余，但必须能从事实表重建。
- 所有写操作必须在同一个 PostgreSQL 事务中写事实表、`audit.events` 和 `job.outbox_events`。
- 金额字段统一使用 `numeric`，Rust 侧使用 decimal 类型；禁止 float/double。
- 常用筛选、排序、关联字段必须拆列，`jsonb` 只保存低频字段、原始 payload、展示补充信息和迁移追溯数据。

## Schema 分层

| Schema | 职责 | 写入方 | 读取方 |
| --- | --- | --- | --- |
| `app` | 核心业务事实表：导入、文件、银行流水、发票、OA 归一化、核销、异常、专题事实。 | Axum API、受控 worker 结果写入 | API、read model 重建任务、审计/运维查询 |
| `read_model` | 工作台、搜索、成本统计、税金抵扣等可重建投影。 | read model worker | API 页面查询、导出 |
| `job` | outbox、worker 任务、attempt、dead letter。 | API、outbox publisher、worker | API 任务状态、worker、运维 |
| `audit` | 审计事件、关键业务变更轨迹。 | API、worker | 审计查询、回滚分析 |
| `staging` | Mongo 迁移、文件解析、OA 同步中间结果。 | 迁移工具、解析 worker、同步 worker | 校验任务、导入确认服务 |

基础扩展建议：

- `pgcrypto`：生成 UUID 和摘要辅助函数。
- `pg_trgm`：名称、票号、摘要等模糊搜索。
- `btree_gin`：组合 GIN 场景的可选补充，不替代常规 B-tree 索引。

公共字段约定：

- 主键：业务事实表使用 `uuid`，默认由应用生成；migration 可使用 `gen_random_uuid()` 作为数据库默认值。
- 时间：统一 `timestamptz`，业务日期另设 `date` 字段。
- 月份分区键：使用对应业务日期归一到月初的 `date`，例如 `txn_month`、`invoice_month`、`approved_month`、`scope_month`。
- 审计字段：核心事实表保留 `created_at`、`created_by`、`updated_at`、`updated_by`；撤销类状态另设 `cancelled_at`、`cancelled_by` 或 `reverted_at`、`reverted_by`。
- 幂等：导入、确认、撤销、worker 写入必须有 `idempotency_key` 或可推导唯一键。
- legacy 追溯：迁移来源表保留 `legacy_collection`、`legacy_id` 或专用 source id 字段。

## 表清单

### app 核心事实表

| 表 | 模块 | 说明 |
| --- | --- | --- |
| `app.import_batches` | 导入 | 一次导入确认或迁移批次的事实头。 |
| `app.import_files` | 导入/文件 | 导入批次内文件记录，关联对象存储。 |
| `app.file_objects` | 文件 | MinIO/S3 对象元数据，替代 GridFS 文件事实。 |
| `app.bank_transactions` | 银行流水 | 银行流水事实，按 `txn_month` 分区。 |
| `app.bank_transaction_categories` | 银行流水 | 分类主记录，支持预付款、预收款、待退款等分类状态。 |
| `app.bank_transaction_category_events` | 银行流水 | 分类变更事件，驱动审计和读模型失效。 |
| `app.invoices` | 发票 | 发票事实，按 `invoice_month` 分区。 |
| `app.invoice_certifications` | 税金 | 已认证/抵扣状态事实。 |
| `app.invoice_inventory_events` | 发票/税金 | 发票库存、认证、状态变化事件。 |
| `app.oa_sync_runs` | OA | OA 同步运行记录。 |
| `app.oa_sync_watermarks` | OA | OA 同步水位，不保存真实凭据。 |
| `app.oa_applications` | OA | OA 表单归一化头表，按 `approved_month` 或 `source_updated_month` 分区。 |
| `app.oa_application_items` | OA | OA 表单明细行、费用项、付款项等拆列结果。 |
| `app.oa_attachments` | OA/文件 | OA 附件元数据和对象存储关系。 |
| `app.reconciliation_cases` | 核销 | 核销关系头，确认、差异、冲销、线下等 case。 |
| `app.reconciliation_case_rows` | 核销 | 核销 case 绑定的银行流水、发票、OA 等对象行。 |
| `app.workbench_row_overrides` | 工作台 | 备注、忽略、人工项目归属等覆盖事实。 |
| `app.workbench_exception_cases` | 异常 | 工作台异常 case 与处理状态。 |
| `app.no_oa_bank_batches` | 免 OA | 免 OA 银行流水批次事实。 |
| `app.turnover_relations` | 往来款 | 往来款、冲抵、外部应收应付关系事实。 |

### read_model 表

| 表 | 说明 |
| --- | --- |
| `read_model.workbench_rows` | 工作台行级投影，按 `scope_month` 分区。 |
| `read_model.workbench_snapshots` | 工作台页面级快照和聚合口径。 |
| `read_model.workbench_candidate_matches` | 自动匹配候选，来源于事实表和匹配规则。 |
| `read_model.search_index_rows` | 全局搜索索引，按 `scope_month` 分区并使用 trigram。 |
| `read_model.cost_statistics_read_models` | 成本统计读模型。 |
| `read_model.tax_offset_read_models` | 税金抵扣读模型。 |

### job、audit、staging 表

| 表 | 说明 |
| --- | --- |
| `job.outbox_events` | 可靠投递事实，业务事务内写入。 |
| `job.worker_tasks` | 任务状态事实，支持查询、取消、人工重放。 |
| `job.worker_attempts` | 每次执行尝试、耗时、错误码和摘要。 |
| `job.dead_letters` | 不再自动重试的失败事件或任务。 |
| `audit.events` | 审计事件，记录操作者、动作、对象、差异和 trace。 |
| `staging.mongo_export_manifest` | Mongo 导出批次、集合、校验摘要和文件清单。 |
| `staging.mongo_import_rows` | app Mongo detailed collections 的通用暂存行。 |
| `staging.import_parse_results` | 文件解析后的结构化行。 |
| `staging.import_parse_issues` | 解析问题、行级错误、警告。 |
| `staging.oa_sync_rows` | OA 同步暂存行，保存 raw payload 和归一化摘要。 |

## 关键字段设计

### `app.import_batches`

关键字段：

- `id uuid primary key`
- `batch_type text not null`
- `source_type text not null`
- `source_name text not null`
- `status text not null`
- `idempotency_key text not null`
- `row_count integer not null default 0`
- `success_count integer not null default 0`
- `error_count integer not null default 0`
- `duplicate_count integer not null default 0`
- `suspected_duplicate_count integer not null default 0`
- `updated_count integer not null default 0`
- `checksum text`
- `legacy_collection text`
- `legacy_id text`
- `created_by text not null`
- `confirmed_at timestamptz`
- `reverted_at timestamptz`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

约束：

- `batch_type in ('output_invoice', 'input_invoice', 'bank_transaction', 'tax_certified', 'etc', 'oa_sync', 'mongo_migration')`
- `status in ('pending', 'completed', 'completed_with_errors', 'reverted', 'failed')`
- `unique (idempotency_key)`
- `unique nulls not distinct (legacy_collection, legacy_id)`

### `app.file_objects` 与 `app.import_files`

`file_objects` 只保存对象元数据：

- `id uuid primary key`
- `storage_provider text not null`
- `bucket text not null`
- `object_key text not null`
- `object_version text`
- `file_name text not null`
- `content_type text`
- `byte_size bigint not null`
- `sha256 text not null`
- `legacy_gridfs_id text`
- `purpose text not null`
- `created_by text`
- `created_at timestamptz not null`

约束和索引：

- `unique (bucket, object_key, object_version)`
- `unique nulls not distinct (legacy_gridfs_id)`
- `check (byte_size >= 0)`
- `index (sha256)`

`import_files` 关联导入批次和文件对象：

- `id uuid primary key`
- `batch_id uuid not null references app.import_batches(id)`
- `file_object_id uuid not null references app.file_objects(id)`
- `file_role text not null`
- `parse_status text not null`
- `row_count integer not null default 0`
- `error_count integer not null default 0`
- `legacy_collection text`
- `legacy_id text`
- `created_at timestamptz not null`

### `app.bank_transactions`

按 `txn_month` range partition。关键字段：

- `id uuid not null`
- `txn_date date not null`
- `txn_month date not null`
- `trade_time timestamptz`
- `pay_receive_time timestamptz`
- `account_no text not null`
- `account_name text`
- `txn_direction text not null`
- `amount numeric(20, 2) not null`
- `signed_amount numeric(20, 2) not null`
- `written_off_amount numeric(20, 2) not null default 0`
- `balance numeric(20, 2)`
- `currency text not null default 'CNY'`
- `counterparty_name_raw text not null`
- `counterparty_name_normalized text`
- `counterparty_account_no text`
- `counterparty_bank_name text`
- `bank_serial_no text`
- `enterprise_serial_no text`
- `source_unique_key text`
- `data_fingerprint text`
- `source_batch_id uuid references app.import_batches(id)`
- `project_id text`
- `status text not null`
- `summary text`
- `remark text`
- `bank_text_fields jsonb not null default '[]'::jsonb`
- `legacy_collection text`
- `legacy_id text`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

约束：

- 分区表主键建议 `primary key (txn_month, id)`，避免 PostgreSQL 分区唯一约束缺少分区键。
- `txn_direction in ('inflow', 'outflow')`
- `status in ('pending', 'partially_reconciled', 'reconciled', 'classified_as_prepayment', 'classified_as_advance_receipt', 'pending_refund', 'pending_counterparty_confirmation')`
- `amount >= 0`
- `written_off_amount >= 0 and written_off_amount <= amount`
- `txn_month = date_trunc('month', txn_date)::date`，可用 generated column 或 check 约束固定。
- 导入幂等：`unique (txn_month, source_batch_id, source_unique_key)` where `source_unique_key is not null`。
- 指纹防重：`unique (txn_month, data_fingerprint)` where `data_fingerprint is not null`。

### `app.invoices`

按 `invoice_month` range partition。关键字段：

- `id uuid not null`
- `invoice_month date not null`
- `invoice_date date`
- `invoice_type text not null`
- `invoice_no text not null`
- `invoice_code text`
- `digital_invoice_no text`
- `source_unique_key text`
- `data_fingerprint text`
- `amount numeric(20, 2) not null`
- `signed_amount numeric(20, 2) not null`
- `tax_amount numeric(20, 2)`
- `total_with_tax numeric(20, 2)`
- `written_off_amount numeric(20, 2) not null default 0`
- `currency text not null default 'CNY'`
- `seller_tax_no text`
- `seller_name text`
- `buyer_tax_no text`
- `buyer_name text`
- `tax_rate numeric(9, 6)`
- `quantity numeric(24, 6)`
- `unit_price numeric(24, 6)`
- `invoice_status_from_source text`
- `status text not null`
- `risk_level text`
- `issuer text`
- `project_id text`
- `department_id text`
- `source_batch_id uuid references app.import_batches(id)`
- `oa_form_id text`
- `etc_invoice_id text`
- `etc_import_batch_id text`
- `etc_submission_batch_id text`
- `etc_submission_status text`
- `workbench_visibility text not null default 'visible'`
- `tags text[] not null default '{}'`
- `source_links jsonb not null default '[]'::jsonb`
- `remark text`
- `legacy_collection text`
- `legacy_id text`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

约束：

- 分区表主键建议 `primary key (invoice_month, id)`。
- `invoice_type in ('output', 'input')`
- `status in ('pending', 'partially_reconciled', 'reconciled', 'pending_offline_confirmation', 'pending_offset', 'pending_invoice_issue', 'pending_invoice_receive')`
- `amount >= 0`
- `written_off_amount >= 0 and written_off_amount <= amount`
- `workbench_visibility in ('visible', 'hidden')`
- 导入幂等：`unique (invoice_month, source_batch_id, source_unique_key)` where `source_unique_key is not null`。
- 票号防重：`unique (invoice_month, invoice_type, invoice_no, invoice_code)` where `invoice_no is not null`；数电票可另设 `unique (invoice_month, invoice_type, digital_invoice_no)` where `digital_invoice_no is not null`。

### OA 归一化表

`app.oa_sync_runs`：

- `id uuid primary key`
- `source_system text not null default 'oa'`
- `scope text not null`
- `triggered_by text not null`
- `status text not null`
- `pulled_count integer not null default 0`
- `success_count integer not null default 0`
- `failed_count integer not null default 0`
- `retry_of_run_id uuid`
- `started_at timestamptz not null`
- `finished_at timestamptz`
- `watermark_before jsonb not null default '{}'::jsonb`
- `watermark_after jsonb not null default '{}'::jsonb`

`app.oa_sync_watermarks`：

- `id uuid primary key`
- `source_system text not null default 'oa'`
- `scope text not null`
- `watermark jsonb not null`
- `last_successful_run_id uuid references app.oa_sync_runs(id)`
- `updated_at timestamptz not null`
- `unique (source_system, scope)`

`app.oa_applications` 按 `approved_month` 或 `source_updated_month` 分区。第一阶段建议使用 `source_updated_month`，因为同步增量和回放以源更新时间水位为主；如工作台主要按审批完成日期查询，可额外索引 `approved_month`。

关键字段：

- `id uuid not null`
- `source_updated_month date not null`
- `approved_month date`
- `oa_source_id text not null`
- `form_type text not null`
- `workflow_no text`
- `title text`
- `status text not null`
- `applicant text`
- `applicant_id text`
- `department_id text`
- `department_name text`
- `project_id text`
- `project_name text`
- `counterparty_name text`
- `amount numeric(20, 2)`
- `currency text not null default 'CNY'`
- `submitted_at timestamptz`
- `approved_at timestamptz`
- `source_updated_at timestamptz not null`
- `sync_run_id uuid references app.oa_sync_runs(id)`
- `normalized_payload jsonb not null default '{}'::jsonb`
- `raw_payload_hash text not null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

约束：

- `primary key (source_updated_month, id)`
- `unique (source_updated_month, oa_source_id)`，如果同一 OA `_id` 可能跨月更新，需要另设非分区全局映射表或接受应用层 upsert 先查旧月。
- `status` 使用 OA 归一化状态 check，例如 `approved`、`in_progress`、`rejected`、`cancelled`、`unknown`。
- `amount is null or amount >= 0`

`app.oa_application_items`：

- `id uuid primary key`
- `application_month date not null`
- `application_id uuid not null`
- `item_type text not null`
- `line_no integer not null`
- `amount numeric(20, 2)`
- `tax_amount numeric(20, 2)`
- `counterparty_name text`
- `project_id text`
- `project_name text`
- `expense_type text`
- `invoice_no text`
- `bank_account_no text`
- `normalized_payload jsonb not null default '{}'::jsonb`
- `unique (application_id, item_type, line_no)`

`app.oa_attachments`：

- `id uuid primary key`
- `application_id uuid not null`
- `file_object_id uuid references app.file_objects(id)`
- `oa_attachment_id text`
- `file_name text not null`
- `content_type text`
- `invoice_cache_key text`
- `parsed_invoice_id uuid`
- `normalized_payload jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null`

### 核销、异常、免 OA 和往来款

`app.reconciliation_cases`：

- `id uuid primary key`
- `case_type text not null`
- `biz_side text not null`
- `counterparty_id text`
- `counterparty_name text`
- `total_amount numeric(20, 2) not null`
- `difference_amount numeric(20, 2) not null default 0`
- `difference_reason text`
- `difference_note text`
- `status text not null`
- `project_id text`
- `approval_form_id text`
- `source_result_id text`
- `exception_code text`
- `resolution_type text`
- `remark text`
- `idempotency_key text not null`
- `confirmed_at timestamptz`
- `cancelled_at timestamptz`
- `created_by text not null`
- `approved_by text`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

约束：

- `case_type in ('automatic', 'manual', 'difference', 'offset', 'offline')`
- `status in ('draft', 'confirmed', 'follow_up_required', 'cancelled')`
- `difference_reason is null or difference_reason in ('fee', 'rounding', 'fx', 'tax', 'other')`
- `unique (idempotency_key)`
- 不物理删除；撤回只改 `status = 'cancelled'` 并写审计事件。

`app.reconciliation_case_rows`：

- `id uuid primary key`
- `case_id uuid not null references app.reconciliation_cases(id)`
- `object_type text not null`
- `object_id uuid not null`
- `object_month date`
- `side_role text not null`
- `applied_amount numeric(20, 2) not null`
- `source_snapshot jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null`

约束：

- `object_type in ('bank_transaction', 'invoice', 'oa_application', 'oa_application_item', 'turnover_relation', 'offline_payment', 'offset_note')`
- `applied_amount >= 0`
- `unique (case_id, object_type, object_id, side_role)`
- 防重复绑定 active case：建议建立部分唯一索引，按业务确认后采用
  `unique (object_type, object_id) where active_binding = true`，或改用 generated/materialized active flag。由于 PostgreSQL partial index 不能跨表引用 case 状态，实际 migration 可在 rows 表冗余 `binding_status` 并由同事务维护。

`app.workbench_row_overrides`：

- `id uuid primary key`
- `row_type text not null`
- `source_object_type text not null`
- `source_object_id uuid not null`
- `scope_month date`
- `override_type text not null`
- `override_payload jsonb not null`
- `status text not null`
- `created_by text not null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`
- `unique (source_object_type, source_object_id, override_type)` where `status = 'active'`

`app.workbench_exception_cases`：

- `id uuid primary key`
- `source_case_id uuid references app.reconciliation_cases(id)`
- `biz_side text not null`
- `exception_code text not null`
- `exception_title text not null`
- `status text not null`
- `resolution_action text`
- `follow_up_ledger_type text`
- `note text`
- `source_invoice_ids uuid[] not null default '{}'`
- `source_bank_txn_ids uuid[] not null default '{}'`
- `created_by text not null`
- `resolved_by text`
- `created_at timestamptz not null`
- `resolved_at timestamptz`

`app.no_oa_bank_batches`：

- `id uuid primary key`
- `scope_month date not null`
- `status text not null`
- `reason text not null`
- `bank_transaction_ids uuid[] not null`
- `total_amount numeric(20, 2) not null`
- `created_by text not null`
- `submitted_at timestamptz`
- `cancelled_at timestamptz`
- `created_at timestamptz not null`

`app.turnover_relations`：

- `id uuid primary key`
- `relation_type text not null`
- `source_object_type text not null`
- `source_object_id uuid not null`
- `counterparty_id text`
- `counterparty_name text`
- `receivable_amount numeric(20, 2) not null default 0`
- `payable_amount numeric(20, 2) not null default 0`
- `offset_amount numeric(20, 2) not null default 0`
- `status text not null`
- `project_id text`
- `note text`
- `created_by text not null`
- `created_at timestamptz not null`
- `cancelled_at timestamptz`

## 金额和精度策略

- 金额：`numeric(20, 2)`，覆盖人民币分精度和大额业务；禁止 `real`、`double precision`、`money`。
- 数量、单价：`numeric(24, 6)`，避免发票行项目数量或单价截断。
- 税率：`numeric(9, 6)`，保存 0.130000 这类比例；展示层再格式化为百分比。
- 已核销金额：事实表冗余 `written_off_amount numeric(20, 2)` 便于查询，但来源必须是有效核销 case 的汇总；撤回 case 时同事务回退。
- signed amount：保留 `signed_amount numeric(20, 2)` 支持方向聚合，约束由应用或 check 保证 `inflow > 0`、`outflow < 0` 的语义一致。
- 所有金额 check 必须覆盖非负字段；允许差异金额为负的字段需要在字段说明里明确。

## 分区策略

第一阶段只对高增长和高频分页查询表分区：

| 表 | 分区键 | 粒度 | 说明 |
| --- | --- | --- | --- |
| `app.bank_transactions` | `txn_month` | 月 | 银行流水天然按交易月查询、导入和撤回。 |
| `app.invoices` | `invoice_month` | 月 | 发票按开票月、认证月、工作台月份查询。 |
| `app.oa_applications` | `source_updated_month` | 月 | 同步增量和回放按源更新时间；另索引 `approved_month`。 |
| `read_model.workbench_rows` | `scope_month` | 月 | 工作台单月查询最频繁。 |
| `read_model.search_index_rows` | `scope_month` | 月，可含 `null` 默认分区 | 全局搜索按月份收敛；无月份实体进入默认分区。 |

分区原则：

- 空库 migration 只创建父表和最近/示例分区的创建函数说明；真实未来分区由运维任务或 migrator 创建，避免在 schema migration 中硬编码生产月份。
- 生产部署必须提前创建未来 3 到 6 个月分区，并监控缺失分区。
- 迁移工具导入历史数据前，先按数据范围创建历史分区。
- 分区表上的唯一约束必须包含分区键；如果业务需要跨月全局唯一，用单独映射表或应用层事务查询补足。
- 老分区可只读归档，但不在第一阶段引入自动 detach/drop。

## 索引策略

### 通用原则

- 高频查询必须有组合 B-tree 索引，索引顺序贴近 `where` 等值字段、范围字段、排序字段。
- `pg_trgm` GIN 只用于模糊搜索字段：票号、往来单位、摘要、项目名、统一搜索文本。
- read model 查询索引优先于事实表跨表拼接。
- 不为低频后台校验字段预建大量索引；迁移和校验可以接受批处理耗时。
- 每个新增索引必须能对应 API、worker 或运维查询场景。

### 事实表索引

`app.bank_transactions`：

- `(txn_month, account_no, txn_date desc, id)`
- `(txn_month, status, txn_date desc)`
- `(txn_month, counterparty_name_normalized)`
- `(txn_month, amount)`
- `(source_batch_id)`
- `(bank_serial_no)` where `bank_serial_no is not null`
- `gin (counterparty_name_raw gin_trgm_ops)`
- `gin (summary gin_trgm_ops)` where `summary is not null`

`app.invoices`：

- `(invoice_month, invoice_type, invoice_no)`
- `(invoice_month, status, invoice_date desc)`
- `(invoice_month, buyer_name)`
- `(invoice_month, seller_name)`
- `(invoice_month, total_with_tax)`
- `(source_batch_id)`
- `gin (invoice_no gin_trgm_ops)`
- `gin (buyer_name gin_trgm_ops)`
- `gin (seller_name gin_trgm_ops)`

`app.oa_applications`：

- `(source_updated_month, source_updated_at desc)`
- `(approved_month, approved_at desc)` where `approved_month is not null`
- `(form_type, status)`
- `(workflow_no)` where `workflow_no is not null`
- `(project_id)`
- `gin (applicant gin_trgm_ops)`
- `gin (project_name gin_trgm_ops)`
- `gin (counterparty_name gin_trgm_ops)`

`app.reconciliation_cases`：

- `(status, created_at desc)`
- `(case_type, status)`
- `(project_id, created_at desc)` where `project_id is not null`
- `(counterparty_id, created_at desc)` where `counterparty_id is not null`

`app.reconciliation_case_rows`：

- `(case_id)`
- `(object_type, object_id)`
- `(object_month, object_type)`
- 部分唯一 active binding 索引待业务确认后落地。

### job、audit、read model 索引

`job.outbox_events`：

- `(status, available_at, created_at)` where `status in ('pending', 'retrying')`
- `(aggregate_type, aggregate_id, created_at desc)`
- `unique (idempotency_key)` where `idempotency_key is not null`

`job.worker_tasks`：

- `(status, available_at, priority desc, created_at)`
- `(task_type, status, created_at desc)`
- `unique (idempotency_key)`

`audit.events`：

- `(entity_type, entity_id, created_at desc)`
- `(actor_id, created_at desc)`
- `(trace_id)` where `trace_id is not null`

`read_model.workbench_rows`：

- `(scope_month, row_type, status, business_date desc, row_id)`
- `(scope_month, source_kind, business_date desc)`
- `(scope_month, relation_case_id)` where `relation_case_id is not null`
- `(scope_month, exception_case_id)` where `exception_case_id is not null`
- `gin (searchable_text gin_trgm_ops)`

`read_model.search_index_rows`：

- `(scope_month, entity_type, updated_at desc)`
- `(entity_type, entity_id)`
- `(scope_month, status)`
- `gin (searchable_text gin_trgm_ops)`

## 约束和状态策略

状态来源优先级：

1. 已在 `backend/src/fin_ops_platform/domain/enums.py` 出现的稳定枚举，第一阶段使用 check constraint。
2. 需要运营配置或未来扩展的状态，使用 reference table；当前未明确需求时暂不引入。
3. OA 原始状态保留 source 字段，同时写归一化状态；原始状态不直接驱动业务逻辑。

建议状态 check：

- `invoice.status` 使用 `InvoiceStatus` 当前枚举。
- `bank_transactions.status` 使用 `TransactionStatus` 当前枚举。
- `reconciliation_cases.status` 使用 `ReconciliationCaseStatus` 当前枚举。
- `import_batches.status` 使用 `BatchStatus` 当前枚举。
- `job.worker_tasks.status` 使用 `queued`、`running`、`succeeded`、`failed`、`retrying`、`dead_lettered`、`cancelled`。
- `job.outbox_events.status` 使用 `pending`、`published`、`retrying`、`dead_lettered`、`cancelled`。

命名约定：

- check：`{table}_{column}_chk`
- foreign key：`{table}_{column}_fkey`
- unique：`{table}_{business_key}_uk`
- index：`{table}_{columns}_idx`
- partial index 后缀：`_active_idx`、`_pending_idx`、`_trgm_idx`

外键策略：

- 同 schema 事实头到事实明细使用外键。
- 分区事实表被跨表引用时，优先在明细表冗余 `object_type/object_id/object_month`，由应用事务校验对象存在，避免跨多父表 polymorphic foreign key。
- staging 表不强制引用 app 事实表，避免迁移重放期间循环依赖。
- read model 表不强制外键到事实表，保证可批量重建和快速 truncate/swap。

## Legacy ID 映射

需要保留两层 legacy 映射：

1. 表内追溯字段：核心迁移表保留 `legacy_collection`、`legacy_id`、`legacy_payload_hash` 或对应 source id。
2. 独立映射表：建议建立 `staging.legacy_id_map`，迁移和回滚期间统一查找。

`staging.legacy_id_map` 字段：

- `id uuid primary key`
- `source_system text not null`
- `legacy_collection text not null`
- `legacy_id text not null`
- `target_schema text not null`
- `target_table text not null`
- `target_id uuid not null`
- `target_partition_month date`
- `payload_hash text`
- `migration_run_id uuid`
- `created_at timestamptz not null`
- `unique (source_system, legacy_collection, legacy_id, target_table)`

当前 Mongo 集合映射：

| Mongo collection/state | PostgreSQL 目标 |
| --- | --- |
| `import_batches` | `app.import_batches` |
| `file_import_sessions` | `app.import_batches`、`app.import_files` |
| `file_import_files` | `app.import_files`、`app.file_objects` |
| GridFS `import_file_blobs` | MinIO/S3 + `app.file_objects` |
| `invoices` | `app.invoices` |
| `bank_transactions` | `app.bank_transactions` |
| `bank_transaction_categories` | `app.bank_transaction_categories`、`app.bank_transaction_category_events` |
| `workbench_row_overrides` | `app.workbench_row_overrides` |
| `workbench_exception_cases` | `app.workbench_exception_cases` |
| `workbench_pair_relations` | `app.reconciliation_cases`、`app.reconciliation_case_rows` |
| `no_oa_bank_batches` | `app.no_oa_bank_batches` |
| `turnover_relations` | `app.turnover_relations` |
| `workbench_read_models` | `read_model.workbench_rows`、`read_model.workbench_snapshots` |
| `workbench_candidate_matches` | `read_model.workbench_candidate_matches` |
| `workbench_matching_dirty_scopes` | `job.worker_tasks` 或 `job.outbox_events` |
| `background_jobs` | `job.worker_tasks`、`job.worker_attempts` |
| `cost_statistics_read_models` | `read_model.cost_statistics_read_models` |
| `tax_offset_read_models` | `read_model.tax_offset_read_models` |
| `oa_sync_state` | `app.oa_sync_watermarks` |
| `oa_attachment_invoice_cache` | `app.oa_attachments` 的解析缓存字段或 staging 缓存 |
| `app_health_alerts` | `audit.events` 或后续运维告警表 |

## Staging 表设计

staging 只服务迁移、解析和同步，不作为正式 API 查询路径。

`staging.mongo_export_manifest`：

- `id uuid primary key`
- `source_database text not null`
- `export_name text not null`
- `exported_at timestamptz not null`
- `collection_count integer not null`
- `document_count bigint not null`
- `sha256_manifest text not null`
- `storage_uri text not null`
- `created_by text not null`
- `created_at timestamptz not null`

`staging.mongo_import_rows`：

- `id uuid primary key`
- `manifest_id uuid references staging.mongo_export_manifest(id)`
- `legacy_collection text not null`
- `legacy_id text not null`
- `row_no bigint not null`
- `payload jsonb not null`
- `payload_hash text not null`
- `target_table text`
- `target_id uuid`
- `status text not null`
- `error_code text`
- `error_message text`
- `created_at timestamptz not null`
- `unique (manifest_id, legacy_collection, legacy_id)`

`staging.import_parse_results`：

- `id uuid primary key`
- `batch_id uuid references app.import_batches(id)`
- `file_id uuid references app.import_files(id)`
- `row_no integer not null`
- `source_record_type text not null`
- `source_unique_key text`
- `data_fingerprint text`
- `decision text not null`
- `decision_reason text`
- `linked_object_type text`
- `linked_object_id uuid`
- `identity_kind text`
- `account_no text`
- `trade_time timestamptz`
- `direction text`
- `amount numeric(20, 2)`
- `counterparty_name text`
- `raw_payload jsonb not null`
- `created_at timestamptz not null`

`staging.import_parse_issues`：

- `id uuid primary key`
- `parse_result_id uuid references staging.import_parse_results(id)`
- `severity text not null`
- `code text not null`
- `message text not null`
- `field_name text`
- `raw_value text`
- `created_at timestamptz not null`

`staging.oa_sync_rows`：

- `id uuid primary key`
- `sync_run_id uuid references app.oa_sync_runs(id)`
- `oa_source_id text not null`
- `form_type text not null`
- `workflow_no text`
- `source_updated_at timestamptz not null`
- `normalized_summary jsonb not null`
- `raw_payload jsonb not null`
- `payload_hash text not null`
- `target_application_id uuid`
- `status text not null`
- `error_code text`
- `error_message text`
- `created_at timestamptz not null`

## Outbox 与任务表

`job.outbox_events`：

- `id uuid primary key`
- `aggregate_type text not null`
- `aggregate_id uuid not null`
- `event_type text not null`
- `payload jsonb not null`
- `status text not null`
- `idempotency_key text`
- `available_at timestamptz not null`
- `published_at timestamptz`
- `attempt_count integer not null default 0`
- `last_error text`
- `trace_id text`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

事件类型第一批：

- `import.batch_confirmed`
- `import.batch_reverted`
- `oa.sync_requested`
- `oa.application_upserted`
- `reconciliation.case_confirmed`
- `reconciliation.case_cancelled`
- `workbench.override_changed`
- `workbench.exception_changed`
- `read_model.rebuild_requested`
- `search.index_update_requested`

`job.worker_tasks`：

- `id uuid primary key`
- `task_type text not null`
- `status text not null`
- `priority integer not null default 0`
- `idempotency_key text not null`
- `payload jsonb not null`
- `available_at timestamptz not null`
- `started_at timestamptz`
- `finished_at timestamptz`
- `locked_by text`
- `locked_at timestamptz`
- `attempt_count integer not null default 0`
- `max_attempts integer not null default 5`
- `last_error_code text`
- `last_error_summary text`
- `created_by text`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

`job.worker_attempts`：

- `id uuid primary key`
- `task_id uuid not null references job.worker_tasks(id)`
- `attempt_no integer not null`
- `worker_id text not null`
- `status text not null`
- `started_at timestamptz not null`
- `finished_at timestamptz`
- `duration_ms integer`
- `error_code text`
- `error_summary text`
- `error_detail jsonb not null default '{}'::jsonb`
- `unique (task_id, attempt_no)`

`job.dead_letters`：

- `id uuid primary key`
- `source_type text not null`
- `source_id uuid not null`
- `reason text not null`
- `payload jsonb not null`
- `last_error_code text`
- `last_error_summary text`
- `replay_status text not null default 'pending'`
- `created_at timestamptz not null`
- `replayed_at timestamptz`

## Read Model 表

`read_model.workbench_rows` 按 `scope_month` 分区：

- `scope_month date not null`
- `row_id uuid not null`
- `row_type text not null`
- `source_kind text not null`
- `source_object_type text not null`
- `source_object_id uuid not null`
- `business_date date`
- `counterparty_name text`
- `project_id text`
- `project_name text`
- `amount numeric(20, 2)`
- `status text not null`
- `group_key text`
- `relation_case_id uuid`
- `candidate_match_id uuid`
- `exception_case_id uuid`
- `searchable_text text not null default ''`
- `payload jsonb not null default '{}'::jsonb`
- `source_versions jsonb not null default '{}'::jsonb`
- `model_version integer not null`
- `is_stale boolean not null default false`
- `updated_at timestamptz not null`
- `primary key (scope_month, row_id)`

`read_model.workbench_snapshots`：

- `id uuid primary key`
- `scope_month date not null`
- `snapshot_type text not null`
- `model_version integer not null`
- `status text not null`
- `payload jsonb not null`
- `source_watermarks jsonb not null`
- `built_at timestamptz not null`
- `unique (scope_month, snapshot_type, model_version)`

`read_model.workbench_candidate_matches`：

- `id uuid primary key`
- `scope_month date not null`
- `candidate_type text not null`
- `confidence text not null`
- `rule_code text not null`
- `explanation text not null`
- `invoice_ids uuid[] not null default '{}'`
- `bank_transaction_ids uuid[] not null default '{}'`
- `oa_application_ids uuid[] not null default '{}'`
- `amount numeric(20, 2) not null default 0`
- `difference_amount numeric(20, 2) not null default 0`
- `counterparty_name text`
- `status text not null`
- `source_versions jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

`read_model.search_index_rows` 按 `scope_month` 分区：

- `scope_month date`
- `id uuid not null`
- `entity_type text not null`
- `entity_id uuid not null`
- `title text not null`
- `subtitle text`
- `searchable_text text not null`
- `amount numeric(20, 2)`
- `status text`
- `payload jsonb not null default '{}'::jsonb`
- `source_version text`
- `updated_at timestamptz not null`
- `primary key (scope_month, id)`；无月份实体可使用默认分区和固定 `scope_month` 占位，或改为非分区表。此点需在实现前确认。

`read_model.cost_statistics_read_models`：

- `id uuid primary key`
- `scope_month date not null`
- `project_id text`
- `cost_category text`
- `amount numeric(20, 2) not null default 0`
- `payload jsonb not null`
- `source_versions jsonb not null`
- `built_at timestamptz not null`
- `unique (scope_month, project_id, cost_category)`

`read_model.tax_offset_read_models`：

- `id uuid primary key`
- `scope_month date not null`
- `invoice_type text`
- `certification_status text`
- `amount numeric(20, 2) not null default 0`
- `tax_amount numeric(20, 2) not null default 0`
- `payload jsonb not null`
- `source_versions jsonb not null`
- `built_at timestamptz not null`
- `unique (scope_month, invoice_type, certification_status)`

读模型重建触发：

- 导入确认/撤回：重建对应 `source_batch_id` 影响月份。
- OA 同步：重建受影响 OA 单据的 `approved_month` 和 `source_updated_month`。
- 核销确认/撤回：重建 case rows 涉及对象月份。
- 异常处理、覆盖变更、免 OA 批次、往来款变更：重建对应 `scope_month`。
- 银行流水分类变更：重建流水月份和成本/工作台相关投影。
- 税金/ETC 导入：重建税金抵扣读模型和相关搜索索引。

## SQLx Migration 顺序

建议拆为只前进的 SQL migration，后续发布后不得编辑既有 migration：

1. `0001_foundation.sql`
   - 创建 schema：`app`、`read_model`、`job`、`audit`、`staging`。
   - 创建扩展：`pgcrypto`、`pg_trgm`、`btree_gin`。
   - 创建公共更新时间触发器函数或约定应用写 `updated_at`。
   - 创建 `audit.events`。
2. `0002_app_imports_files.sql`
   - `app.import_batches`、`app.file_objects`、`app.import_files`。
   - staging 解析结果可在此或第 5 步创建，避免导入确认没有暂存表。
3. `0003_app_financial_facts.sql`
   - `app.bank_transactions`、`app.invoices`、分类和发票事件表。
   - 创建分区父表、分区创建辅助函数和关键索引。
4. `0004_app_oa_reconciliation.sql`
   - OA 同步、OA 归一化、附件、核销、异常、免 OA、往来款事实表。
5. `0005_job_outbox_audit.sql`
   - `job.outbox_events`、`worker_tasks`、`worker_attempts`、`dead_letters`。
   - 补充 outbox/worker 状态索引。
6. `0006_staging_migration.sql`
   - `staging.mongo_export_manifest`、`mongo_import_rows`、`legacy_id_map`、`import_parse_results`、`import_parse_issues`、`oa_sync_rows`。
7. `0007_read_models.sql`
   - `read_model.workbench_rows`、`workbench_snapshots`、`workbench_candidate_matches`、`search_index_rows`、成本和税金读模型。
   - 创建 read model 分区和搜索索引。
8. `0008_seed_reference_data.sql`，可选
   - 仅当采用 reference table 管理状态或类型时使用。
   - 不写生产凭据，不写环境相关配置。

执行约束：

- 空库应能按顺序执行。
- migration 不依赖生产数据。
- 分区父表必须先于引用它的 read model 重建逻辑存在。
- 对大表新增索引在生产后续变更中使用 `create index concurrently`，但首次空库 migration 可以普通创建。
- SQLx 离线校验应在 Rust skeleton 确认 crate 和 `DATABASE_URL` 管理方式后再接入，本文件不预设真实连接串。

## EXPLAIN 验证清单

后续 migration 和 API 查询落地后，至少对以下查询执行 `EXPLAIN (ANALYZE, BUFFERS)`，并记录计划、行数估算和 P95 样本：

1. 单月工作台分页：按 `scope_month`、`row_type`、`status`、`business_date desc` 查询 `read_model.workbench_rows`。
2. 工作台模糊搜索：单月 `counterparty/project/summary` 搜索，确认命中 `workbench_rows` trigram 索引或统一搜索表。
3. 银行流水列表：按 `txn_month`、账号、日期范围分页。
4. 银行流水模糊查往来单位：确认只扫描目标月份分区并使用 `counterparty_name_raw` trigram。
5. 发票列表：按 `invoice_month`、`invoice_type`、`status`、`invoice_date desc` 分页。
6. 发票票号/购销方搜索：确认 `invoice_no`、`buyer_name`、`seller_name` trigram 索引生效。
7. OA 单据同步回放查询：按 `source_updated_month` 和 `source_updated_at` 范围扫描。
8. 核销对象定位：通过 `reconciliation_case_rows(object_type, object_id)` 找 active case。
9. outbox publisher 拉取：按 `status in pending/retrying`、`available_at <= now()` 获取下一批事件，确认不全表扫描。
10. worker 拉取任务：按 `status`、`available_at`、`priority` 获取下一批任务。
11. 全局搜索：按 `scope_month`、`entity_type`、`searchable_text` 查询 `read_model.search_index_rows`。
12. 成本统计和税金抵扣读模型：按 `scope_month`、`project_id` 或认证状态查询。

验收阈值需要结合迁移后数据规模确定。第一阶段建议记录：

- 是否发生不必要的跨分区扫描。
- 是否发生大表 sequential scan。
- 估算行数和实际行数偏差是否超过一个数量级。
- 排序是否使用索引顺序，是否出现高内存 sort。
- trigram 搜索是否因查询词过短退化，需要 API 层最小关键词长度。

## 未决问题

1. `app.oa_applications` 分区键最终选择：同步友好的 `source_updated_month`，还是工作台查询友好的 `approved_month`。当前建议使用 `source_updated_month` 并索引 `approved_month`。
2. 跨月全局唯一约束策略：发票号码、OA `_id`、银行流水 source key 如果必须全局唯一，分区父表约束无法直接表达，需要独立映射表或应用层事务校验。
3. 核销 active binding 约束：是否允许同一对象参与多个 active case。若不允许，需要在 rows 表冗余 `binding_status` 并用部分唯一索引约束。
4. `search_index_rows` 是否允许 `scope_month null`。PostgreSQL 分区主键和唯一约束不适合 nullable 分区键，需在实现前决定默认月份、默认分区或非分区表。
5. OA 表单类型和状态的完整枚举需要由 OA 同步负责人确认；当前仅设计归一化字段和 source payload 保留策略。
6. 成本统计、税金抵扣、ETC 的最终事实表是否独立落在 `app` schema，还需对应产品规格和后续子代理设计确认；本文先保留 read model 和发票认证相关基础。
7. 文件对象 `bucket/object_key/object_version` 是否需要跨环境全局唯一，取决于 MinIO/S3 bucket 命名策略。
8. reference table 与 check constraint 的取舍：第一阶段建议对稳定枚举用 check，未来需要运营配置时再迁移到 reference table。
9. SQLx migration 目录位置需要等 Axum/Rust skeleton 确认，避免与后续 crate 初始化冲突。
10. 历史 Mongo 导出格式、payload hash 算法和 legacy `_id` 字符串化规则需要迁移工具子任务统一。

