# Read Model 和搜索索引设计

## 目标和原则

本文定义 Axum + PostgreSQL 目标架构中的 read model、搜索索引、失效和重建策略。

目标：

- 工作台、全局搜索、成本统计、税金抵扣等重查询不在页面请求中实时拼全量数据。
- 页面优先读取 PostgreSQL read model；事实变更通过 outbox 触发增量重建。
- `read_model.search_index_rows` 承担统一搜索，不跨多张事实表实时模糊查询。
- read model 可以冗余，但必须能从 PostgreSQL 事实表和 OA 归一化表重建。
- 单月 scope 优先，`all` 汇总异步增量聚合，不阻塞单月操作。

事实源：

- 银行流水、发票、导入、核销、异常、免 OA、分类等事实来自 `app` schema。
- OA 事实来自同步后的 `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`，不在页面请求中扫描 OA Mongo。
- read model 状态、重建任务和索引更新通过 `job.outbox_events`、`job.worker_tasks` 和 Python Worker 协议推进。
- Redis 只能缓存短期查询结果或广播进度，不能作为 read model 或搜索索引事实源。

## Scope 和版本

统一 scope 规则：

| 字段 | 规则 |
| --- | --- |
| `scope_month` | 月份 read model 使用当月第一天 `date`，例如 `2026-05-01`。 |
| `scope_key` | 字符串定位一个投影，例如 `workbench:2026-05`、`cost:active:2026-05`、`tax_offset:2026-05`、`workbench:all`。 |
| `scope_type` | `month` 或 `all_time`。 |
| `source_versions` | 记录影响投影的事实版本、规则版本、快照 hash。版本不一致即 stale。 |
| `generated_at` | 投影生成时间，不代表事实更新时间。 |
| `stale_reason` | 最近一次失效原因，例如 `import.batch_confirmed`、`oa.synced`、`relation.cancelled`。 |

当前 Python `WorkbenchReadModelService` 已使用 `source_versions` 判断新鲜度，包含 `exception_rules_version`、`exception_projection_version`、`case_snapshot_version`、`pair_relation_snapshot_version`、`candidate_snapshot_version`、`turnover_relation_snapshot_version`、`matching_rules_version`。目标模型保留这个思想，但把版本持久化到 PostgreSQL 表字段中。

## 读模型表

### 工作台行级投影 `read_model.workbench_rows`

用途：支撑工作台分页、筛选、定位、搜索跳转和局部重建。

```sql
create table read_model.workbench_rows (
  id uuid not null,
  scope_month date not null,
  scope_key text not null,
  row_id uuid not null,
  row_type text not null,
  source_kind text not null,
  source_entity_type text not null,
  source_entity_id uuid not null,
  business_date date,
  counterparty_name text,
  project_id text,
  project_name text,
  amount numeric(18, 2),
  direction text,
  status text not null,
  zone_hint text not null,
  group_key text,
  relation_case_id uuid,
  candidate_match_id uuid,
  exception_case_id uuid,
  ignored boolean not null default false,
  handled_exception boolean not null default false,
  payload jsonb not null default '{}'::jsonb,
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default now(),
  stale boolean not null default false,
  stale_reason text,
  updated_at timestamptz not null default now(),
  constraint workbench_row_type_chk check (row_type in ('oa', 'bank', 'invoice')),
  constraint workbench_zone_hint_chk check (zone_hint in ('paired', 'open', 'ignored', 'processed_exception'))
) partition by range (scope_month);

create unique index workbench_rows_scope_id_uidx
  on read_model.workbench_rows (scope_month, id);

create unique index workbench_rows_scope_row_uidx
  on read_model.workbench_rows (scope_month, row_type, row_id);

create index workbench_rows_filter_idx
  on read_model.workbench_rows (scope_month, row_type, status, business_date desc);

create index workbench_rows_relation_idx
  on read_model.workbench_rows (relation_case_id)
  where relation_case_id is not null;

create index workbench_rows_counterparty_trgm_idx
  on read_model.workbench_rows using gin (counterparty_name gin_trgm_ops);
```

事实来源：

- `app.bank_transactions`
- `app.invoices`
- `app.oa_applications`
- `app.oa_application_items`
- `app.oa_attachments`
- `app.reconciliation_cases`
- `app.reconciliation_case_rows`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.no_oa_bank_batches`
- `app.turnover_relations`

投影约束：

- `payload` 保存页面显示所需的 `summary_fields`、`detail_fields`、`available_actions`、跳转辅助字段。
- 常用筛选字段必须拆列，不允许只依赖 `payload` 查询。
- `row_id` 对应业务行稳定 ID；`source_entity_id` 指向事实表主键。
- `status` 表示业务状态，`zone_hint` 表示页面区域提示，二者不要混用。

### 工作台页面快照 `read_model.workbench_snapshots`

用途：快速返回单月或 all-time 页面级结构，减少 API 组装成本。

```sql
create table read_model.workbench_snapshots (
  scope_key text primary key,
  scope_type text not null,
  scope_month date,
  schema_version text not null,
  payload jsonb not null,
  ignored_rows jsonb not null default '[]'::jsonb,
  summary jsonb not null default '{}'::jsonb,
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null,
  stale boolean not null default false,
  stale_reason text,
  rebuild_task_id uuid,
  updated_at timestamptz not null default now(),
  constraint workbench_snapshot_scope_type_chk check (scope_type in ('month', 'all_time'))
);

create index workbench_snapshots_month_idx
  on read_model.workbench_snapshots (scope_month);
```

查询口径：

- 单月工作台先查 `workbench_snapshots`，若新鲜则直接返回。
- 需要分页、筛选、定位、搜索跳转时查 `workbench_rows`。
- `workbench:all` 只用于汇总或低频全局视图，由后台聚合，不能在请求中全量拼装。

### 候选匹配 `read_model.workbench_candidate_matches`

用途：保存自动匹配候选和解释，不作为已确认核销事实。

```sql
create table read_model.workbench_candidate_matches (
  id uuid primary key,
  scope_month date not null,
  candidate_key text not null,
  oa_application_id uuid,
  bank_transaction_id uuid,
  invoice_id uuid,
  score numeric(8, 4) not null,
  reasons jsonb not null default '[]'::jsonb,
  status text not null default 'active',
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint candidate_match_status_chk check (status in ('active', 'superseded', 'dismissed'))
);

create unique index workbench_candidate_matches_key_uidx
  on read_model.workbench_candidate_matches (scope_month, candidate_key);
```

确认核销时写 `app.reconciliation_cases` 和 `app.reconciliation_case_rows`；候选匹配只提供建议。

### 成本统计 `read_model.cost_statistics_read_models`

当前 Python 服务使用 `scope_key = {project_scope}:{month}`，其中 `project_scope in ('active', 'all')`，月份可为 `YYYY-MM` 或 `all`。目标表延续该 scope。

```sql
create table read_model.cost_statistics_read_models (
  scope_key text primary key,
  scope_type text not null,
  scope_month date,
  project_scope text not null,
  schema_version text not null,
  payload jsonb not null,
  summary jsonb not null default '{}'::jsonb,
  entry_count integer not null default 0,
  source_scope_keys text[] not null default '{}',
  source_versions jsonb not null default '{}'::jsonb,
  cache_status text not null default 'ready',
  generated_at timestamptz not null,
  stale boolean not null default false,
  stale_reason text,
  rebuild_task_id uuid,
  updated_at timestamptz not null default now(),
  constraint cost_project_scope_chk check (project_scope in ('active', 'all')),
  constraint cost_cache_status_chk check (cache_status in ('ready', 'stale', 'rebuilding', 'failed'))
);

create index cost_statistics_scope_month_idx
  on read_model.cost_statistics_read_models (scope_month, project_scope);
```

事实来源：

- 银行流水及分类。
- 项目状态和项目口径设置。
- 核销关系、免 OA、异常处理。
- OA 项目和费用字段。

### 税金抵扣 `read_model.tax_offset_read_models`

当前 Python 服务使用 `scope_key = YYYY-MM`，且 payload 必须包含 `output_items`、`input_plan_items`、`certified_items`。目标表延续单月口径，不提供 `all` scope。

```sql
create table read_model.tax_offset_read_models (
  scope_key text primary key,
  scope_month date not null,
  schema_version text not null,
  payload jsonb not null,
  output_count integer not null default 0,
  input_plan_count integer not null default 0,
  certified_count integer not null default 0,
  source_scope_keys text[] not null default '{}',
  source_versions jsonb not null default '{}'::jsonb,
  cache_status text not null default 'ready',
  generated_at timestamptz not null,
  stale boolean not null default false,
  stale_reason text,
  rebuild_task_id uuid,
  updated_at timestamptz not null default now(),
  constraint tax_offset_cache_status_chk check (cache_status in ('ready', 'stale', 'rebuilding', 'failed'))
);

create index tax_offset_scope_month_idx
  on read_model.tax_offset_read_models (scope_month);
```

事实来源：

- 输出发票。
- 输入发票。
- 认证记录。
- OA 附件发票投影。
- 税金/ETC 专题导入确认结果。

## 统一搜索表 `read_model.search_index_rows`

全局搜索只查 `search_index_rows`，不在请求中遍历工作台 snapshot 或跨事实表做实时模糊搜索。

```sql
create table read_model.search_index_rows (
  id uuid not null,
  entity_type text not null,
  entity_id uuid not null,
  source_kind text not null,
  scope_month date not null,
  title text not null,
  subtitle text,
  searchable_text text not null,
  searchable_tokens jsonb not null default '{}'::jsonb,
  amount numeric(18, 2),
  status text,
  zone_hint text,
  project_id text,
  project_name text,
  jump_target jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default now(),
  stale boolean not null default false,
  stale_reason text,
  updated_at timestamptz not null default now(),
  constraint search_entity_type_chk check (
    entity_type in (
      'oa_application',
      'oa_attachment',
      'bank_transaction',
      'invoice',
      'reconciliation_case',
      'project'
    )
  )
) partition by range (scope_month);

create unique index search_index_rows_scope_id_uidx
  on read_model.search_index_rows (scope_month, id);

create unique index search_index_rows_entity_uidx
  on read_model.search_index_rows (scope_month, entity_type, entity_id);

create index search_index_rows_scope_idx
  on read_model.search_index_rows (scope_month, entity_type, status);

create index search_index_rows_project_idx
  on read_model.search_index_rows (project_id, scope_month)
  where project_id is not null;

create index search_index_rows_text_trgm_idx
  on read_model.search_index_rows using gin (searchable_text gin_trgm_ops);
```

`searchable_text` 组装规则：

- OA：流程编号、申请人、项目名称、费用类型、费用内容、对方户名、申请事由、金额、月份。
- 银行流水：流水 ID、对方户名、金额、支付账户、企业流水号、凭证号、账号、交易时间、备注、摘要、资金方向、项目名称。
- 发票：发票号码、发票代码、数电发票号码、销方/购方名称、纳税人识别号、金额、开票日期、发票类型、项目名称。
- 项目：项目编号、项目名称、状态、客户或甲方名称。
- `scope_month` 必须非空。跨月或全局实体按可跳转月份生成多行；确实没有月份的配置型实体不进入该分区表，改由对应设置接口查询。

查询规则：

- API 入参限制 `limit <= 100`，默认 20。
- `scope` 过滤映射到 `entity_type` 集合，例如 `oa`、`bank`、`invoice`、`all`。
- `month=all` 查询最近活跃月份优先，不能无界扫描；需要分页游标或按更新时间/月份倒序限制。
- 模糊搜索使用 `pg_trgm`；未来如需要中文分词，可在同一表增加 `tsvector` 列，不改变 API 口径。
- 返回结果必须包含 `jump_target`，用于跳转到工作台月份、row_id、record_type、zone_hint 和 group_id。

## 失效和重建触发

所有写操作先更新事实表，再在同一事务写 outbox。Worker 根据事件计算影响 scope。

| 触发事件 | 影响 read model | Scope 计算 |
| --- | --- | --- |
| 导入文件解析完成 | 通常不失效正式 read model；更新导入预览状态。 | `import_file_id`。 |
| 导入确认 `import.batch_confirmed` | `workbench_rows`、`workbench_snapshots`、`search_index_rows`、成本统计、税金抵扣。 | 银行流水按 `txn_month`；发票按 `invoice_month/issued_at`；税金按发票月份。 |
| 导入撤回 `import.batch_reverted` | 同导入确认，并删除或标记相关搜索行。 | 原 batch 影响月份。 |
| OA 同步完成 `oa.synced` | 工作台、搜索、成本统计、税金抵扣中涉及 OA 附件发票的月份。 | `approved_at`、`source_updated_at`、附件发票开票月、显式 dirty scopes。 |
| 核销确认/撤销 | 工作台、搜索、成本统计。 | 参与 case 的 OA、流水、发票所在月份；跨月 case 触发多个单月。 |
| 异常处理/撤销 | 工作台、搜索、成本统计。 | 异常关联 row 所在月份。 |
| 忽略、备注、覆盖字段变更 | 工作台、搜索。 | 被覆盖 row 所在月份。 |
| 免 OA 批次提交/撤回/stale | 工作台、搜索、成本统计。 | 批次内流水月份。 |
| 银行流水分类变更 | 工作台、搜索、成本统计。 | 流水月份；`all` 成本汇总异步。 |
| 项目状态设置变更 | 成本统计、工作台搜索展示字段。 | 受影响项目关联月份；无法精确时标记 project scope 的 all-time 后台重建。 |
| 税金/ETC 导入确认 | 税金抵扣、成本统计、搜索。 | 导入记录月份和附件发票月份。 |

Outbox 事件建议：

| 事件 | payload 必需字段 |
| --- | --- |
| `read_model.rebuild_requested` | `models`、`scope_keys`、`months`、`reason`、`source_versions`。 |
| `search.index_requested` | `mode`、`entity_type`、`entity_ids` 或 `scope_months`、`reason`。 |
| `read_model.mark_stale_requested` | `models`、`scope_keys`、`stale_reason`。 |

## Stale 策略

读路径必须明确处理 read model 缺失或过期。

| 场景 | 行为 |
| --- | --- |
| 单月 snapshot 新鲜 | 直接返回 snapshot，并附带 `cache_status='ready'`、`generated_at`。 |
| 单月 snapshot 缺失 | API 创建或复用 `read_model.rebuild` 任务，返回 `202 Accepted` 或轻量空态；不在请求中全量重建。 |
| 单月 snapshot stale 但有旧数据 | 默认返回旧数据，响应标记 `cache_status='stale'`、`stale_reason`、`rebuild_task_id`，后台重建。高风险确认页面可要求前端刷新后再提交。 |
| 单月 snapshot stale 且超过最大容忍时间 | 返回 `409 Conflict` 或 `503 Service Unavailable`，提示正在重建，避免展示明显错误口径。最大容忍时间按页面配置，初始建议 10 分钟。 |
| `all` 汇总 stale | 返回最近一次汇总并标记 stale；后台重建。不得阻塞单月操作。 |
| 搜索索引 stale | 对 stale 行降权或过滤，响应标记 `index_status='stale'`；若全局索引重建中，限制为已知新鲜月份。 |
| Worker 重建失败 | 保留旧 read model，状态 `failed`，记录任务 ID 和错误摘要；不删除旧投影。 |

新鲜度判断：

- API 根据 `source_versions` 和 `stale=false` 判断。
- 每个模型有可选 `max_age_seconds`，但时间老化只作为告警或低风险缓存刷新依据，不能替代事实版本。
- 写操作的正确性不得依赖 stale read model；提交确认时必须重新读取事实表并验证约束。

## 重建策略

工作台重建：

1. Worker 获取 `model='workbench'` 和 scope。
2. 读取对应月份事实表和关系表。
3. 生成 `workbench_rows` 临时结果。
4. 在事务内删除或覆盖该月份旧 rows，upsert 新 rows，写 snapshot 和 metadata。
5. 标记相关 `search_index_rows` 更新。

建议使用同月事务边界：

- 单月 `workbench_rows` 重建必须原子替换，避免页面读到半新半旧投影。
- `all` snapshot 可独立重建，不与单月事务耦合。
- 同一 `model + scope_key` 使用 advisory lock 或任务唯一约束串行执行。

搜索索引更新：

- `upsert`：事实实体新增或变更时按实体生成一行。
- `delete`：事实撤回、软删除或不可见时删除搜索行，或标记 `status='deleted'` 并默认过滤。
- `rebuild_scope`：按月份删除并重建该月所有相关实体搜索行。
- 搜索索引更新可以晚于工作台重建，但必须有滞后指标和 stale 标记。

成本统计重建：

- 单月 active/all 项目 scope 独立重建。
- 月份变更同时标记 `cost:active:all` 和 `cost:all:all` stale，由后台增量聚合。
- 项目状态变更优先重建 active scope；all scope 保留历史全量口径。

税金抵扣重建：

- 只按月份重建。
- 输入/输出发票、认证记录、OA 附件发票变化触发对应月份。
- 银行流水导入默认不触发税金抵扣，除非该导入明确包含税金/ETC 专题事实。

## API 查询口径

工作台：

- `GET /workbench?month=YYYY-MM` 读取 `read_model.workbench_snapshots`。
- 筛选、分页、定位接口读取 `read_model.workbench_rows`。
- 详情接口可读取事实表补充完整字段，但不能触发 OA Mongo 实时扫描。

搜索：

- `GET /search?q=...` 只查 `read_model.search_index_rows`。
- 返回按 `entity_type` 分组的摘要，跳转字段来自 `jump_target`。
- 搜索结果展示状态来自 `status/zone_hint`，不要重新计算核销关系。

成本统计：

- `GET /cost-statistics?month=YYYY-MM&project_scope=active|all` 读取 `read_model.cost_statistics_read_models`。
- cache miss 创建重建任务；是否返回旧数据遵循 stale 策略。

税金抵扣：

- `GET /tax-offset?month=YYYY-MM` 读取 `read_model.tax_offset_read_models`。
- cache miss 创建重建任务或在低数据量 staging 环境同步构建；生产请求路径默认不做全量构建。

## 监控指标

Prometheus 指标建议：

| 指标 | 类型 | 标签 | 含义 |
| --- | --- | --- | --- |
| `finops_read_model_cache_requests_total` | counter | `model,result` | read model 命中、miss、stale 返回、失败。 |
| `finops_read_model_rebuild_total` | counter | `model,scope_type,result,reason` | 重建任务结果。 |
| `finops_read_model_rebuild_duration_seconds` | histogram | `model,scope_type` | 重建耗时。 |
| `finops_read_model_stale_total` | gauge | `model,scope_type,reason` | 当前 stale scope 数。 |
| `finops_read_model_oldest_stale_seconds` | gauge | `model` | 最老 stale scope 时长。 |
| `finops_workbench_rows_total` | gauge | `scope_month,row_type,status` | 工作台投影行数。 |
| `finops_search_index_rows_total` | gauge | `entity_type,scope_month` | 搜索索引行数。 |
| `finops_search_query_duration_seconds` | histogram | `scope,month,result` | 搜索查询耗时。 |
| `finops_search_index_lag_seconds` | gauge | `entity_type` | 事实更新时间到索引更新时间的滞后。 |
| `finops_search_index_update_total` | counter | `entity_type,mode,result` | 索引 upsert/delete/rebuild 结果。 |
| `finops_cost_statistics_rebuild_duration_seconds` | histogram | `project_scope,scope_type` | 成本统计重建耗时。 |
| `finops_tax_offset_rebuild_duration_seconds` | histogram | `scope_month,result` | 税金抵扣重建耗时。 |

初始性能目标沿用迁移路线：

| 场景 | 数据规模 | 目标 |
| --- | --- | --- |
| 单月工作台 read model 命中 | 10 万流水/发票 | P95 < 300ms |
| 单月工作台 read model 命中 | 100 万流水/发票 | P95 < 800ms |
| 全局搜索 | 100 万搜索行 | P95 < 500ms |
| read model 重建 | 单月 10 万行 | 目标 < 60s，后台执行 |

## 验收清单

- 每个 read model 都能列出事实来源、scope、版本字段和重建触发事件。
- 页面请求不扫描 OA Mongo，不实时拼全量工作台。
- `search_index_rows` 有 `pg_trgm` GIN 索引、scope 索引和稳定跳转 payload。
- stale 时的返回、重建和错误策略明确。
- 重建任务使用 outbox + NATS + Worker 协议，状态可查询、失败可重试、dead letter 可审计。
- 核心 API 上线前保留 SQL、参数规模、`EXPLAIN ANALYZE`、P95/P99 和索引命中记录。
