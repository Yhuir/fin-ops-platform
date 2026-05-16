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
| `stale_reason` | 最近一次失效原因，例如 `import.batch_confirmed`、`oa.synced`、`reconciliation.revoked`。 |

当前 Python `WorkbenchReadModelService` 已使用 `source_versions` 判断新鲜度，包含 `exception_rules_version`、`exception_projection_version`、`case_snapshot_version`、`pair_relation_snapshot_version`、`candidate_snapshot_version`、`turnover_relation_snapshot_version`、`matching_rules_version`。目标模型保留这个思想，但把版本持久化到 PostgreSQL 表字段中。

P2-08D 统一字段口径：

| 字段 | 口径 |
| --- | --- |
| `stale` | `true` 表示投影已知落后于事实或规则版本；`false` 只表示生成时使用的 `source_versions` 与 Worker 当时观测到的事实版本一致。 |
| `stale_reason` | 机器可读原因，使用 `{domain}.{event_or_condition}`，例如 `import.batch_confirmed`、`oa.synced`、`reconciliation.confirmed`、`rules.changed`、`rebuild.failed`、`dependency.stale`。 |
| `source_versions` | JSON 对象，必须包含影响该 scope 的事实水位、规则版本和依赖投影版本；不能放 secret、URI、原始文件内容或用户输入全文。 |
| `generated_at` | Worker 成功生成并提交 read model 的时间，用于观察投影年龄；不得作为事实更新时间，也不得单独判断新鲜。 |
| `updated_at` | read model 行被写入、标记 stale 或失败状态更新的时间，用于运维排序和 stale age 指标。 |
| `rebuild_task_id` | 最近一次负责该 scope 的 `job.worker_tasks.id`；API 返回给前端用于查询重建状态。 |

`source_versions` 推荐键：

| 键 | 含义 |
| --- | --- |
| `fact_updated_at` | 参与重建的事实行最大 `updated_at`，用于统一滞后指标。 |
| `{table}_max_updated_at` | 关键事实表水位，例如 `bank_transactions_max_updated_at`、`invoices_max_updated_at`、`reconciliation_cases_max_updated_at`。 |
| `{domain}_version` | 有单调版本时写业务版本，例如 `matching_rules_version`、`exception_rules_version`。 |
| `{model}_generated_at` | 依赖其他 read model 时记录依赖投影生成时间，例如 `workbench_rows_generated_at`。 |
| `{model}_source_hash` | 对依赖版本集合做 hash，避免 payload 过大。 |

新鲜度判断必须同时满足：`stale=false`、`source_versions` 覆盖当前请求所需事实水位；带 `cache_status` 的页面级或统计级投影还必须满足 `cache_status='ready'`。`max_age_seconds` 只能作为告警或低风险刷新依据，不能替代版本匹配。

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

## P2-08C 成本统计和税金抵扣重建

本节只定义 PostgreSQL read model 重建策略。Worker 从 PostgreSQL 事实表和同步后的 OA 归一化表读取数据，不访问 OA 源库；API 请求路径只读取 read model，不做全量重建。

### 现有业务口径冻结

成本统计沿用当前 Python `CostStatisticsReadModelService` 口径：

- `schema_version = '2026-05-cost-statistics-explorer-v1'`。
- `scope_key = {project_scope}:{month}`，`project_scope in ('active', 'all')`，`month` 为 `YYYY-MM` 或 `all`。
- 单月 scope 的 `scope_type = 'month'`，`active:all` 和 `all:all` 的 `scope_type = 'all_time'`。
- `entry_count` 优先等于 `payload.summary.transaction_count`；缺失时才回退为 `payload.time_rows` 长度。
- `source_scope_keys` 保留来源 scope，例如 `workbench:2026-05`、`search:2026-05`、`cost:active:2026-05`。
- `project_scope='active'` 只包含当前业务口径下的 active 项目；`project_scope='all'` 保留全量项目口径，不因 active 状态过滤而丢历史项目。

税金抵扣沿用当前 Python `TaxOffsetReadModelService` 口径：

- `schema_version = '2026-05-tax-offset-month-v1'`。
- `scope_key = YYYY-MM`，只支持单月 scope，不提供 `all` 汇总。
- payload 必须包含 `output_items`、`input_plan_items`、`certified_items` 三个数组；缺失任意数组即重建失败。
- `output_count`、`input_plan_count`、`certified_count` 分别等于三个数组长度，不允许由 Worker 静默修正。

### 影响范围计算

成本统计的增量重建按月份和项目 scope 拆任务：

| 触发来源 | 影响 scope | 说明 |
| --- | --- | --- |
| 银行导入确认/撤回 | `active:YYYY-MM`、`all:YYYY-MM`；异步标记 `active:all`、`all:all`。 | 月份来自流水交易日期或导入归属月。 |
| 核销确认/撤销 | 参与 case 的流水、OA、发票所在月份。 | 跨月 case 拆成多个单月任务。 |
| 异常处理、免 OA 批次提交/撤回 | 关联流水月份。 | 只影响成本统计和工作台/搜索，不影响税金抵扣。 |
| 银行流水分类变更 | 流水月份。 | 分类口径进入 `payload.summary` 和分组行。 |
| 项目状态或项目口径设置变更 | 已知项目关联月份；无法精确时只标记 all-time stale 并排队按月补偿。 | 不在请求路径全量扫描所有历史月份。 |
| OA 同步归一化完成 | 涉及 OA 项目和费用字段的月份。 | 只读取 `app.oa_*` 归一化表。 |

税金抵扣的增量重建只按月份拆任务：

| 触发来源 | 影响 scope | 说明 |
| --- | --- | --- |
| 输出发票导入确认/撤回 | 发票开票月或业务归属月。 | 重建 `output_items`。 |
| 输入发票导入确认/撤回 | 发票开票月或业务归属月。 | 重建 `input_plan_items`。 |
| 认证记录导入确认/撤回 | 认证月份；若关联发票月份不同，也排对应发票月份。 | 重建 `certified_items`。 |
| OA 附件发票投影更新 | 附件发票开票月。 | 只处理同步后的附件发票投影。 |
| 银行流水导入 | 默认不触发。 | 除非导入类型明确包含税金/ETC 专题事实。 |

### Worker 任务和 all-time 异步

推荐统一使用 `read_model.rebuild_requested` outbox payload，并通过 `models` 区分目标：

```json
{
  "models": ["cost_statistics"],
  "scope_keys": ["active:2026-05", "all:2026-05"],
  "months": ["2026-05"],
  "reason": "import.batch_confirmed",
  "source_versions": {
    "bank_transactions_max_updated_at": "2026-05-16T08:30:00Z",
    "reconciliation_cases_max_updated_at": "2026-05-16T08:30:00Z",
    "rules_version": "cost-statistics-v1"
  }
}
```

```json
{
  "models": ["tax_offset"],
  "scope_keys": ["2026-05"],
  "months": ["2026-05"],
  "reason": "tax.import_confirmed",
  "source_versions": {
    "invoice_max_updated_at": "2026-05-16T08:30:00Z",
    "tax_certification_max_updated_at": "2026-05-16T08:30:00Z",
    "rules_version": "tax-offset-v1"
  }
}
```

Worker 执行规则：

1. 对每个 `model + scope_key` 获取任务唯一约束或 advisory lock，避免同一 scope 并发覆盖。
2. 将目标 read model 标记为 `cache_status='rebuilding'`，保留旧 payload。
3. 从 PostgreSQL 事实表和 OA 归一化表读取影响范围，生成完整 payload。
4. 在单个事务中 upsert read model、写入 `source_versions`、清除 `stale`，并记录 `generated_at`。
5. 重建失败时保留旧 payload，设置 `cache_status='failed'`、`stale=true`、`stale_reason` 和 `rebuild_task_id`；错误摘要进入 job attempt，不暴露 secret 或内部栈。

成本统计 all-time 只由后台任务异步聚合，不和单月任务绑在同一请求或同一事务中。单月事实变更只标记 `active:all`、`all:all` stale，并排队低优先级 `scope_type='all_time'` 任务。all-time Worker 优先读取已经新鲜的单月 `cost_statistics_read_models`；如果发现参与月份 stale 或缺失，先阻断 all-time 发布并继续保留旧 all-time payload。

税金抵扣不生成 all-time read model。需要跨月分析时由离线报表或后台汇总任务另建专题投影，不能复用 `tax_offset_read_models` 的请求路径。

### Upsert 和 stale SQL 模板

成本统计单月 upsert：

```sql
insert into read_model.cost_statistics_read_models (
  scope_key,
  scope_type,
  scope_month,
  project_scope,
  schema_version,
  payload,
  summary,
  entry_count,
  source_scope_keys,
  source_versions,
  cache_status,
  generated_at,
  stale,
  stale_reason,
  rebuild_task_id,
  updated_at
) values (
  $1::text,
  case when $2::text = 'all' then 'all_time' else 'month' end,
  case when $2::text = 'all' then null else to_date($2::text || '-01', 'YYYY-MM-DD') end,
  $3::text,
  '2026-05-cost-statistics-explorer-v1',
  $4::jsonb,
  coalesce($4::jsonb -> 'summary', '{}'::jsonb),
  coalesce(nullif($4::jsonb #>> '{summary,transaction_count}', '')::integer, jsonb_array_length(coalesce($4::jsonb -> 'time_rows', '[]'::jsonb))),
  $5::text[],
  $6::jsonb,
  'ready',
  now(),
  false,
  null,
  $7::uuid,
  now()
)
on conflict (scope_key) do update set
  scope_type = excluded.scope_type,
  scope_month = excluded.scope_month,
  project_scope = excluded.project_scope,
  schema_version = excluded.schema_version,
  payload = excluded.payload,
  summary = excluded.summary,
  entry_count = excluded.entry_count,
  source_scope_keys = excluded.source_scope_keys,
  source_versions = excluded.source_versions,
  cache_status = 'ready',
  generated_at = excluded.generated_at,
  stale = false,
  stale_reason = null,
  rebuild_task_id = excluded.rebuild_task_id,
  updated_at = now();
```

税金抵扣单月 upsert：

```sql
insert into read_model.tax_offset_read_models (
  scope_key,
  scope_month,
  schema_version,
  payload,
  output_count,
  input_plan_count,
  certified_count,
  source_scope_keys,
  source_versions,
  cache_status,
  generated_at,
  stale,
  stale_reason,
  rebuild_task_id,
  updated_at
) values (
  $1::text,
  to_date($1::text || '-01', 'YYYY-MM-DD'),
  '2026-05-tax-offset-month-v1',
  $2::jsonb,
  jsonb_array_length($2::jsonb -> 'output_items'),
  jsonb_array_length($2::jsonb -> 'input_plan_items'),
  jsonb_array_length($2::jsonb -> 'certified_items'),
  $3::text[],
  $4::jsonb,
  'ready',
  now(),
  false,
  null,
  $5::uuid,
  now()
)
on conflict (scope_key) do update set
  scope_month = excluded.scope_month,
  schema_version = excluded.schema_version,
  payload = excluded.payload,
  output_count = excluded.output_count,
  input_plan_count = excluded.input_plan_count,
  certified_count = excluded.certified_count,
  source_scope_keys = excluded.source_scope_keys,
  source_versions = excluded.source_versions,
  cache_status = 'ready',
  generated_at = excluded.generated_at,
  stale = false,
  stale_reason = null,
  rebuild_task_id = excluded.rebuild_task_id,
  updated_at = now();
```

stale 标记模板：

```sql
update read_model.cost_statistics_read_models
set stale = true,
    cache_status = 'stale',
    stale_reason = $2::text,
    rebuild_task_id = $3::uuid,
    updated_at = now()
where scope_key = any($1::text[]);

update read_model.tax_offset_read_models
set stale = true,
    cache_status = 'stale',
    stale_reason = $2::text,
    rebuild_task_id = $3::uuid,
    updated_at = now()
where scope_key = any($1::text[]);
```

### 对账样例

Worker 发布前必须执行结构对账，失败时阻断 `ready` 状态发布。

成本统计最低对账：

```sql
select
  scope_key,
  entry_count,
  nullif(payload #>> '{summary,transaction_count}', '')::integer as payload_transaction_count,
  jsonb_array_length(coalesce(payload -> 'time_rows', '[]'::jsonb)) as time_row_count
from read_model.cost_statistics_read_models
where scope_key = any($1::text[])
  and (
    entry_count <> coalesce(nullif(payload #>> '{summary,transaction_count}', '')::integer, jsonb_array_length(coalesce(payload -> 'time_rows', '[]'::jsonb)))
    or schema_version <> '2026-05-cost-statistics-explorer-v1'
    or cache_status <> 'ready'
    or stale
  );
```

税金抵扣最低对账：

```sql
select
  scope_key,
  output_count,
  jsonb_array_length(payload -> 'output_items') as payload_output_count,
  input_plan_count,
  jsonb_array_length(payload -> 'input_plan_items') as payload_input_plan_count,
  certified_count,
  jsonb_array_length(payload -> 'certified_items') as payload_certified_count
from read_model.tax_offset_read_models
where scope_key = any($1::text[])
  and (
    output_count <> jsonb_array_length(payload -> 'output_items')
    or input_plan_count <> jsonb_array_length(payload -> 'input_plan_items')
    or certified_count <> jsonb_array_length(payload -> 'certified_items')
    or schema_version <> '2026-05-tax-offset-month-v1'
    or cache_status <> 'ready'
    or stale
  );
```

金额类对账由 Worker 在生成 payload 时同时输出 report 行，字段至少包含 `model`、`scope_key`、`month`、`project_scope`、`metric`、`expected_amount`、`actual_amount`、`diff_amount`、`source_scope_keys`。任一金额差异非零、计数差异非零、必需数组缺失或 schema version 不匹配都必须让任务失败，不能发布为 `ready`。

测试 fixture：

- `docs/dev/api-fixtures/cost-statistics-read-model-rebuild-fixture.json`
- `docs/dev/api-fixtures/tax-offset-read-model-rebuild-fixture.json`

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

### P2-08B 增量重建策略

`read_model.search_index_rows` 的更新只由 outbox + Worker 触发，不在搜索请求路径中跨 `app.bank_transactions`、`app.invoices`、`app.oa_applications`、`app.reconciliation_cases` 等事实表实时拼装。搜索 API 的唯一数据源是 `read_model.search_index_rows`。

Worker 消息使用 `finops.jobs.search.index`，对应 `search.index_requested` payload：

```json
{
  "mode": "upsert",
  "entity_type": "bank_transaction",
  "entity_ids": ["uuid"],
  "scope_months": ["2026-05-01"],
  "reason": "import.batch_confirmed",
  "source_versions": {
    "fact_version": "42",
    "workbench_projection_version": "sha256"
  }
}
```

模式约束：

| mode | 适用场景 | 行为 |
| --- | --- | --- |
| `upsert` | 单个或一批实体新增、字段变更、状态变更。 | 按 `scope_month + entity_type + entity_id` upsert 一行，更新 `searchable_text`、`jump_target`、`source_versions`、`generated_at`，清除 stale。 |
| `delete` | 导入撤回、软删除、实体不可见。 | 删除指定实体的索引行；若需要审计展示，事实保留在 app 表，不把搜索行标为可见。 |
| `mark_stale` | 写事务已提交但重建尚未完成。 | 标记指定 scope/entity 为 stale，搜索 API 可降权或过滤。 |
| `rebuild_scope` | 单月补偿重建、dry-run 修复、分区重建。 | 先构建同月临时结果，再原子 upsert，并删除本次范围内已经不存在的旧索引行。 |

`jump_target` 稳定形状：

```json
{
  "route": "workbench",
  "month": "2026-05",
  "scope_month": "2026-05-01",
  "entity_type": "bank_transaction",
  "entity_id": "uuid",
  "record_type": "bank",
  "row_id": "uuid",
  "zone_hint": "open",
  "group_id": null
}
```

规则：

- `route='workbench'` 表示前端跳到工作台定位；`route='detail'` 可用于尚无工作台 row 的实体详情页。
- `scope_month` 必须是月初日期；`month` 只给前端展示和路由兼容。
- `entity_type/entity_id` 是事实实体定位；`record_type/row_id/zone_hint/group_id` 是工作台定位辅助字段。
- Worker 可以读取已生成的 `read_model.workbench_rows` 来补全 `zone_hint/group_id`，但搜索 API 不能在请求路径实时回查工作台或事实表补字段。

Entity 映射：

| `entity_type` | 来源 | `scope_month` | `jump_target` |
| --- | --- | --- | --- |
| `bank_transaction` | `app.bank_transactions` | `txn_month` | 优先工作台 `record_type='bank'`；无工作台 row 时跳银行流水详情。 |
| `invoice` | `app.invoices` | `invoice_month` | 优先工作台 `record_type='invoice'`；无工作台 row 时跳发票详情。 |
| `oa_application` | `app.oa_applications` | `coalesce(approved_month, source_updated_month)` | 优先工作台 `record_type='oa'`；无工作台 row 时跳 OA 详情。 |
| `oa_attachment` | `app.oa_attachments` + 所属 `app.oa_applications` | 所属 OA 的 `coalesce(approved_month, source_updated_month)`，或已解析发票的 `parsed_invoice_month` | 跳 OA 附件或对应工作台 OA 行。 |
| `reconciliation_case` | `app.reconciliation_cases` + `app.reconciliation_case_rows` | case rows 的 `object_month`；跨月 case 每月一行 | 跳工作台 case/group 或核销详情。 |
| `project` | 项目设置事实或 OA/银行/发票中项目引用 | 项目活跃事实月份；无月份的配置型项目不进入该分区表 | 跳项目相关工作台月份或项目详情。 |

`project` 不得触发无界全量索引。项目状态或名称变更时，先由写事务计算受影响月份；无法精确计算时只标记相关 all-time 统计 stale，并拆成按月后台任务。

通用 upsert 模板：

```sql
insert into read_model.search_index_rows (
  id,
  entity_type,
  entity_id,
  source_kind,
  scope_month,
  title,
  subtitle,
  searchable_text,
  searchable_tokens,
  amount,
  status,
  zone_hint,
  project_id,
  project_name,
  jump_target,
  payload,
  source_versions,
  generated_at,
  stale,
  stale_reason
)
select
  gen_random_uuid(),
  source.entity_type,
  source.entity_id,
  source.source_kind,
  source.scope_month,
  source.title,
  source.subtitle,
  source.searchable_text,
  source.searchable_tokens,
  source.amount,
  source.status,
  source.zone_hint,
  source.project_id,
  source.project_name,
  source.jump_target,
  source.payload,
  source.source_versions,
  now(),
  false,
  null
from search_index_source_rows source
on conflict (scope_month, entity_type, entity_id)
do update set
  title = excluded.title,
  subtitle = excluded.subtitle,
  searchable_text = excluded.searchable_text,
  searchable_tokens = excluded.searchable_tokens,
  amount = excluded.amount,
  status = excluded.status,
  zone_hint = excluded.zone_hint,
  project_id = excluded.project_id,
  project_name = excluded.project_name,
  jump_target = excluded.jump_target,
  payload = excluded.payload,
  source_versions = excluded.source_versions,
  generated_at = excluded.generated_at,
  stale = false,
  stale_reason = null,
  updated_at = now();
```

银行流水 upsert source 示例：

```sql
with requested as (
  select
    $1::date as scope_month,
    $2::uuid[] as entity_ids,
    $3::jsonb as source_versions
),
search_index_source_rows as (
  select
    'bank_transaction'::text as entity_type,
    b.id as entity_id,
    'app.bank_transactions'::text as source_kind,
    b.txn_month as scope_month,
    coalesce(nullif(b.counterparty_name_raw, ''), '银行流水') as title,
    concat_ws(' · ', b.account_name, b.account_no, b.txn_direction) as subtitle,
    concat_ws(
      ' ',
      b.id::text,
      b.counterparty_name_raw,
      b.counterparty_name_normalized,
      b.account_no,
      b.account_name,
      b.counterparty_account_no,
      b.counterparty_bank_name,
      b.bank_serial_no,
      b.enterprise_serial_no,
      b.summary,
      b.remark,
      b.txn_direction,
      b.amount::text,
      b.txn_date::text,
      b.project_id
    ) as searchable_text,
    jsonb_build_object(
      'counterparty', b.counterparty_name_normalized,
      'serial_no', coalesce(b.bank_serial_no, b.enterprise_serial_no),
      'direction', b.txn_direction
    ) as searchable_tokens,
    b.amount,
    b.status,
    coalesce(w.zone_hint, 'open') as zone_hint,
    b.project_id,
    w.project_name,
    jsonb_build_object(
      'route', 'workbench',
      'month', to_char(b.txn_month, 'YYYY-MM'),
      'scope_month', b.txn_month,
      'entity_type', 'bank_transaction',
      'entity_id', b.id,
      'record_type', 'bank',
      'row_id', coalesce(w.row_id, b.id),
      'zone_hint', coalesce(w.zone_hint, 'open'),
      'group_id', w.group_key
    ) as jump_target,
    jsonb_build_object(
      'txn_date', b.txn_date,
      'account_no', b.account_no,
      'currency', b.currency
    ) as payload,
    requested.source_versions
  from app.bank_transactions b
  join requested on requested.scope_month = b.txn_month
  left join read_model.workbench_rows w
    on w.scope_month = b.txn_month
   and w.source_entity_type = 'bank_transaction'
   and w.source_entity_id = b.id
   and not w.stale
  where requested.entity_ids is null or b.id = any(requested.entity_ids)
)
select * from search_index_source_rows;
```

发票 upsert source 示例：

```sql
with requested as (
  select
    $1::date as scope_month,
    $2::uuid[] as entity_ids,
    $3::jsonb as source_versions
),
search_index_source_rows as (
  select
    'invoice'::text as entity_type,
    i.id as entity_id,
    'app.invoices'::text as source_kind,
    i.invoice_month as scope_month,
    coalesce(i.invoice_no, i.digital_invoice_no, i.seller_name, '发票') as title,
    concat_ws(' · ', i.invoice_type, i.seller_name, i.buyer_name) as subtitle,
    concat_ws(
      ' ',
      i.id::text,
      i.invoice_no,
      i.invoice_code,
      i.digital_invoice_no,
      i.seller_name,
      i.seller_tax_no,
      i.buyer_name,
      i.buyer_tax_no,
      i.amount::text,
      i.total_with_tax::text,
      i.invoice_date::text,
      i.invoice_type,
      i.status,
      i.project_id,
      i.remark
    ) as searchable_text,
    jsonb_build_object(
      'invoice_no', coalesce(i.invoice_no, i.digital_invoice_no),
      'seller', i.seller_name,
      'buyer', i.buyer_name
    ) as searchable_tokens,
    coalesce(i.total_with_tax, i.amount) as amount,
    i.status,
    coalesce(w.zone_hint, 'open') as zone_hint,
    i.project_id,
    w.project_name,
    jsonb_build_object(
      'route', 'workbench',
      'month', to_char(i.invoice_month, 'YYYY-MM'),
      'scope_month', i.invoice_month,
      'entity_type', 'invoice',
      'entity_id', i.id,
      'record_type', 'invoice',
      'row_id', coalesce(w.row_id, i.id),
      'zone_hint', coalesce(w.zone_hint, 'open'),
      'group_id', w.group_key
    ) as jump_target,
    jsonb_build_object(
      'invoice_type', i.invoice_type,
      'invoice_date', i.invoice_date,
      'currency', i.currency
    ) as payload,
    requested.source_versions
  from app.invoices i
  join requested on requested.scope_month = i.invoice_month
  left join read_model.workbench_rows w
    on w.scope_month = i.invoice_month
   and w.source_entity_type = 'invoice'
   and w.source_entity_id = i.id
   and not w.stale
  where i.workbench_visibility = 'visible'
    and (requested.entity_ids is null or i.id = any(requested.entity_ids))
)
select * from search_index_source_rows;
```

OA application upsert source 示例：

```sql
with requested as (
  select
    $1::date as scope_month,
    $2::uuid[] as entity_ids,
    $3::jsonb as source_versions
),
search_index_source_rows as (
  select
    'oa_application'::text as entity_type,
    oa.id as entity_id,
    'app.oa_applications'::text as source_kind,
    coalesce(oa.approved_month, oa.source_updated_month) as scope_month,
    coalesce(oa.workflow_no, oa.title, oa.project_name, 'OA') as title,
    concat_ws(' · ', oa.form_type, oa.applicant, oa.counterparty_name) as subtitle,
    concat_ws(
      ' ',
      oa.id::text,
      oa.oa_source_id,
      oa.workflow_no,
      oa.title,
      oa.form_type,
      oa.status,
      oa.applicant,
      oa.department_name,
      oa.project_id,
      oa.project_name,
      oa.counterparty_name,
      oa.amount::text,
      oa.submitted_at::text,
      oa.approved_at::text
    ) as searchable_text,
    jsonb_build_object(
      'workflow_no', oa.workflow_no,
      'applicant', oa.applicant,
      'form_type', oa.form_type
    ) as searchable_tokens,
    oa.amount,
    oa.status,
    coalesce(w.zone_hint, 'open') as zone_hint,
    oa.project_id,
    oa.project_name,
    jsonb_build_object(
      'route', 'workbench',
      'month', to_char(coalesce(oa.approved_month, oa.source_updated_month), 'YYYY-MM'),
      'scope_month', coalesce(oa.approved_month, oa.source_updated_month),
      'entity_type', 'oa_application',
      'entity_id', oa.id,
      'record_type', 'oa',
      'row_id', coalesce(w.row_id, oa.id),
      'zone_hint', coalesce(w.zone_hint, 'open'),
      'group_id', w.group_key
    ) as jump_target,
    jsonb_build_object(
      'oa_source_id', oa.oa_source_id,
      'workflow_no', oa.workflow_no,
      'form_type', oa.form_type
    ) as payload,
    requested.source_versions
  from app.oa_applications oa
  join requested on requested.scope_month = coalesce(oa.approved_month, oa.source_updated_month)
  left join read_model.workbench_rows w
    on w.scope_month = coalesce(oa.approved_month, oa.source_updated_month)
   and w.source_entity_type = 'oa_application'
   and w.source_entity_id = oa.id
   and not w.stale
  where requested.entity_ids is null or oa.id = any(requested.entity_ids)
)
select * from search_index_source_rows;
```

`delete` 模板：

```sql
delete from read_model.search_index_rows
where scope_month = $1::date
  and entity_type = $2::text
  and entity_id = any($3::uuid[]);
```

`mark_stale` 模板：

```sql
update read_model.search_index_rows
set
  stale = true,
  stale_reason = $4::text,
  updated_at = now()
where scope_month = any($1::date[])
  and ($2::text[] is null or entity_type = any($2::text[]))
  and ($3::uuid[] is null or entity_id = any($3::uuid[]));
```

`rebuild_scope` 模板：

```sql
begin;

select read_model.create_search_index_rows_partition($1::date);

create temporary table search_index_rebuild_rows
(like read_model.search_index_rows including defaults)
on commit drop;

-- Worker 按 entity_type 调用各自 source SQL，把目标月份结果写入临时表。
insert into search_index_rebuild_rows (...)
select ...;

insert into read_model.search_index_rows (...)
select ... from search_index_rebuild_rows
on conflict (scope_month, entity_type, entity_id)
do update set
  title = excluded.title,
  subtitle = excluded.subtitle,
  searchable_text = excluded.searchable_text,
  searchable_tokens = excluded.searchable_tokens,
  amount = excluded.amount,
  status = excluded.status,
  zone_hint = excluded.zone_hint,
  project_id = excluded.project_id,
  project_name = excluded.project_name,
  jump_target = excluded.jump_target,
  payload = excluded.payload,
  source_versions = excluded.source_versions,
  generated_at = excluded.generated_at,
  stale = false,
  stale_reason = null,
  updated_at = now();

delete from read_model.search_index_rows existing
where existing.scope_month = $1::date
  and existing.entity_type = any($2::text[])
  and not exists (
    select 1
    from search_index_rebuild_rows rebuilt
    where rebuilt.scope_month = existing.scope_month
      and rebuilt.entity_type = existing.entity_type
      and rebuilt.entity_id = existing.entity_id
  );

commit;
```

`rebuild_scope` 不跨所有历史月份执行。全局修复必须拆成多个 `scope_month` worker task，按月份串行或有限并发执行。

搜索查询模板：

```sql
select
  entity_type,
  entity_id,
  scope_month,
  title,
  subtitle,
  amount,
  status,
  zone_hint,
  project_id,
  project_name,
  jump_target,
  similarity(searchable_text, $1::text) as score,
  generated_at,
  stale
from read_model.search_index_rows
where scope_month = any($2::date[])
  and entity_type = any($3::text[])
  and not stale
  and searchable_text % $1::text
order by scope_month desc, score desc, updated_at desc
limit least($4::integer, 100);
```

查询约束：

- `month=YYYY-MM` 映射到单个 `scope_month`，可直接命中分区。
- `month=all` 必须先解析最近活跃月份列表，例如最近 12 个月或有权限的月份游标，再传入 `scope_month = any($months)`；不得无界扫描所有分区。
- API 可以对 stale 行降权或过滤。第一版默认 `and not stale`，并在响应 metadata 中报告 `index_status`。

滞后和 stale 指标：

```sql
-- stale 行数
select entity_type, scope_month, stale_reason, count(*) as stale_rows
from read_model.search_index_rows
where stale
group by entity_type, scope_month, stale_reason;

-- 最老 stale 秒数
select entity_type, extract(epoch from now() - min(updated_at))::bigint as oldest_stale_seconds
from read_model.search_index_rows
where stale
group by entity_type;

-- 索引滞后：generated_at 代表索引生成时间；fact_updated_at 由 payload 或 source_versions 写入。
select
  entity_type,
  max(
    extract(
      epoch from (
        generated_at
        - nullif(source_versions ->> 'fact_updated_at', '')::timestamptz
      )
    )
  ) as max_lag_seconds
from read_model.search_index_rows
where source_versions ? 'fact_updated_at'
group by entity_type;
```

Worker 必须在 `source_versions` 写入足以观测滞后的版本，例如 `fact_updated_at`、`fact_version`、`workbench_projection_version`。如果某类事实没有单调版本，先写 `fact_updated_at=max(updated_at)`，后续再升级为事件版本。

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

## P2-08D Stale 和重建调度协议

### `stale_reason` 标准值

`stale_reason` 面向机器处理和运维聚合，不写自然语言长句。展示文案由 API 或前端按错误码映射。

| 原因 | 适用场景 | 默认可重试 |
| --- | --- | --- |
| `import.batch_confirmed` | 导入确认后事实新增或覆盖。 | 是 |
| `import.batch_reverted` | 导入撤回后旧投影需要删除或重算。 | 是 |
| `oa.synced` | OA 归一化表增量同步完成。 | 是 |
| `reconciliation.confirmed` | 核销确认改变工作台、搜索、成本统计。 | 是 |
| `reconciliation.revoked` | 核销撤销改变工作台、搜索、成本统计。 | 是 |
| `exception.updated` | 异常处理、撤销或规则投影改变。 | 是 |
| `no_oa_batch.updated` | 免 OA 批次提交、撤回或 stale。 | 是 |
| `classification.changed` | 银行流水分类改变。 | 是 |
| `project_scope.changed` | 项目 active/all 口径改变。 | 是 |
| `tax.import_confirmed` | 税金、发票或认证专题导入确认。 | 是 |
| `rules.changed` | 匹配、异常、成本或税金业务规则版本改变。 | 是 |
| `dependency.stale` | 依赖的 read model stale 或缺失，例如 all-time 依赖单月。 | 是 |
| `rebuild.failed` | 最近一次重建失败但保留旧投影。 | 取决于错误码 |
| `manual.invalidate` | 运维或修复任务显式标记 stale。 | 是 |

### `read_model.rebuild_requested` outbox payload

写事实的事务负责计算影响范围，并在同一事务写入 `job.outbox_events`。该事件只请求重建，不携带大 payload，不携带 secret，不直接修改 read model。

```json
{
  "schema_version": "finops.read_model.rebuild_requested.v1",
  "models": ["workbench", "search_index", "cost_statistics", "tax_offset"],
  "scope_keys": ["workbench:2026-05", "active:2026-05", "2026-05"],
  "months": ["2026-05"],
  "scope_type": "month",
  "reason": "import.batch_confirmed",
  "source": {
    "aggregate_type": "import_batch",
    "aggregate_id": "uuid",
    "event_id": "uuid"
  },
  "source_versions": {
    "fact_updated_at": "2026-05-16T08:30:00Z",
    "bank_transactions_max_updated_at": "2026-05-16T08:30:00Z",
    "rules_version": "read-model-rules-v1"
  },
  "priority": "normal",
  "force": false,
  "requested_by": "system"
}
```

字段约束：

| 字段 | 规则 |
| --- | --- |
| `schema_version` | 必须等于 `finops.read_model.rebuild_requested.v1`；不支持版本进入 dead letter，不猜测兼容。 |
| `models` | 允许值：`workbench`、`search_index`、`cost_statistics`、`tax_offset`。多个模型可同事件请求，但 Worker 必须拆成单模型任务。 |
| `scope_keys` | 必须是目标模型稳定 scope key。缺失时 Worker 可由 `models + months + scope_type` 推导；推导失败则 dead letter。 |
| `months` | `YYYY-MM` 字符串数组；全局修复也必须拆成多个单月任务。 |
| `scope_type` | `month` 或 `all_time`；`all_time` 只能用于后台聚合，不阻塞单月 API。 |
| `reason` | 必须来自 `stale_reason` 标准值或明确登记的新值。 |
| `source_versions` | 必须足以让 Worker 判断幂等和新鲜度；缺关键水位时任务失败，不发布 `ready` 投影。 |
| `priority` | `high`、`normal`、`low`；用户可见页面缺失通常为 `high`，all-time 聚合为 `low`。 |
| `force` | `true` 只表示即使现有投影看似新鲜也重建；不能跳过版本记录、对账或事务边界。 |

Outbox 落表建议：

| 字段 | 值 |
| --- | --- |
| `event_type` | `read_model.rebuild_requested` |
| `subject` | `finops.jobs.read_model.rebuild` |
| `aggregate_type` | 触发源，例如 `import_batch`、`reconciliation_case`、`system_rebuild` |
| `aggregate_id` | 触发源主键；系统批量任务使用该任务 ID |
| `idempotency_key` | `read_model.rebuild:{model}:{scope_key}:{hash(source_versions)}:{reason}`；多模型事件拆任务后按单模型生成 |

`read_model.mark_stale_requested` 用于先标记、后排队。payload 至少包含：

```json
{
  "schema_version": "finops.read_model.mark_stale_requested.v1",
  "models": ["workbench"],
  "scope_keys": ["workbench:2026-05"],
  "stale_reason": "reconciliation.confirmed",
  "source_versions": {
    "fact_updated_at": "2026-05-16T08:30:00Z"
  },
  "rebuild": {
    "enqueue": true,
    "priority": "normal"
  }
}
```

### 调度流程

1. 写事务提交事实、审计、`read_model.mark_stale_requested` 或 `read_model.rebuild_requested` outbox。
2. Publisher 只负责投递到 `finops.jobs.read_model.rebuild`，不解释 payload。
3. Worker 校验 payload schema、模型、scope、source_versions 和 `job.worker_tasks` 幂等键。
4. Worker 对每个 `model + scope_key` 获取 advisory lock；同一 scope 已有 running 任务时，新任务可合并为待重建版本或直接结束为 `result_summary.coalesced=true`。
5. Worker 将目标 scope 标记 `cache_status='rebuilding'`，写 `rebuild_task_id`，保留旧 payload。
6. Worker 生成新投影并执行模型内对账；对账通过后同事务 upsert read model、清除 stale、写 `generated_at/source_versions`。
7. Worker 成功后按需投递下游 `search.index_requested` 或 all-time 聚合重建任务。
8. Worker 失败时保留旧投影，写失败状态和可查询任务结果。

### 失败、重试和 dead letter

| 失败类型 | 示例 | 任务状态 | read model 状态 | NATS ack 策略 |
| --- | --- | --- | --- | --- |
| 可重试依赖失败 | PostgreSQL 短暂不可用、对象存储临时错误、锁超时。 | `retrying`，写 `next_attempt_at`。 | 保留旧投影；若已标记 stale，继续 stale。 | `nak` 或延迟重投。 |
| 依赖 stale | all-time 聚合发现参与单月 stale 或缺失。 | `retrying` 或 `failed`，视是否已有依赖重建任务。 | all-time 保留旧投影并标记 `dependency.stale`。 | 已排依赖任务时 `ack`。 |
| 业务对账失败 | count、amount、checksum 或 payload 必需字段不一致。 | `failed`，`retryable=false`。 | 保留旧投影，`cache_status='failed'`、`stale=true`、`stale_reason='rebuild.failed'`。 | `ack`，等待修复后人工重放。 |
| Payload 不兼容 | schema version 不支持、scope 无法解析、source_versions 缺关键水位。 | `dead_lettered`。 | 不覆盖旧投影；可标记 `rebuild.failed`。 | `ack` 并写 `job.dead_letters`。 |
| 重试耗尽 | 超过 `max_attempts`。 | `dead_lettered`。 | 保留旧投影和最后失败摘要。 | `ack` 并写 `job.dead_letters`。 |

退避建议：

- 默认 `max_attempts=5`。
- `BackOff`：30 秒、2 分钟、10 分钟、30 分钟、2 小时。
- 用户请求导致的 `high` 优先级任务可以从 10 秒开始，但不得绕过同 scope 串行锁。
- dead letter 重放必须创建新的 outbox event 和新的 worker task，不能把旧任务原地改回 `queued`。

### API stale/missing 响应

所有读取 read model 的 API 响应都应携带一致的 cache metadata：

```json
{
  "cache": {
    "status": "ready",
    "scope_key": "workbench:2026-05",
    "generated_at": "2026-05-16T08:30:00Z",
    "stale": false,
    "stale_reason": null,
    "rebuild_task_id": null,
    "source_versions": {}
  }
}
```

响应策略：

| 场景 | HTTP | Body 口径 | 是否创建任务 |
| --- | --- | --- | --- |
| read model 新鲜 | `200 OK` | 返回数据，`cache.status='ready'`。 | 否 |
| read model 缺失且低风险页面可等待 | `202 Accepted` | 返回空数据或轻量占位，`cache.status='missing'`、`rebuild_task_id`。 | 是，创建或复用 |
| read model 缺失且页面必须有数据 | `503 Service Unavailable` | 不返回伪数据，提示正在重建，带 `rebuild_task_id`。 | 是，创建或复用 |
| read model stale 但未超过容忍时间 | `200 OK` | 返回旧数据，`cache.status='stale'`、`stale_reason`、`rebuild_task_id`。 | 是，复用优先 |
| read model stale 且超过容忍时间 | `409 Conflict` 或 `503 Service Unavailable` | 不返回可能误导的旧口径；高风险页面优先 `409`。 | 是，复用优先 |
| 最近一次重建失败但有旧数据 | `200 OK` 或 `409 Conflict` | 低风险只读可返回旧数据并带 `cache.status='failed'`；确认/写入前页面必须阻断。 | 人工或自动重试按错误类型 |
| 搜索索引部分 stale | `200 OK` | 默认过滤 stale 行，metadata 写 `index_status='partial_stale'`。 | 是 |

API 不得在请求路径扫描 OA 源库或全量拼装 all-time。写 API 的正确性不得依赖 read model；提交前必须读取事实表并重新验证约束。

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

### Axum Worker 增量重建实现边界

`rust/fin-ops-api` 的 `read_model.rebuild` Worker 第一版只消费已落入 PostgreSQL 的 facts/read models，不访问 OA 源 Mongo，也不修改业务 API routes 或 outbox publisher。请求 payload 支持按 `models + scope_keys + months` 拆分目标 scope，当前支持：

| model | scope_key | scope_month | 事实来源 | 发布目标 |
| --- | --- | --- | --- | --- |
| `workbench` | `workbench:YYYY-MM` | 必填，月初日期 | `app.bank_transactions`、`app.invoices`、`app.oa_applications`、核销/异常/覆盖 facts | `read_model.workbench_rows`、`read_model.workbench_snapshots` |
| `search_index` | `search:YYYY-MM` | 必填，月初日期 | PostgreSQL facts + 已生成的同月 `read_model.workbench_rows` 跳转辅助字段 | `read_model.search_index_rows` |
| `cost_statistics` | `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all` | 单月或后台 all-time | 银行流水、分类、核销、免 OA、异常、OA 项目字段 | `read_model.cost_statistics_read_models` |
| `tax_offset` | `YYYY-MM` | 必填，月初日期 | 输出/输入发票、认证记录、OA 附件发票投影、税金/ETC 专题导入事实 | `read_model.tax_offset_read_models` |

执行约束：

- Worker 不在 API 请求路径执行全量 all-time 重算；`all` 只作为后台统计 scope，单月事实变更应拆成 bounded monthly tasks。
- `source_versions` 和 `source_watermark` 二选一作为事实水位输入，二者都出现时以 `source_versions` 为准；缺少 `fact_updated_at` 时任务失败，不猜测水位。
- 成功发布必须写入 `source_versions`、`schema_version`、`generated_at`、`rebuild_task_id` 并清除 stale；API metadata 用 `rebuilt_at` 作为 `generated_at` 的外部别名。
- stale age 不落成单独事实字段；读取时按 `now() - updated_at` 计算 `stale_seconds`，ready 投影返回 `0`。
- 搜索索引 scope rebuild 先按月创建分区和临时表，只删除同月旧索引行；不会扫描或删除所有历史月份。
- 缺失 source contract 时必须记录 blocker，例如某类候选匹配或项目设置 facts 未落 PostgreSQL 时不能从 Mongo 或旧 Python app state 回填。

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
