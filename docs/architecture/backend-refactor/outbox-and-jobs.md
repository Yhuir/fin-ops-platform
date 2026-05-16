# Outbox、任务队列和 Python Worker 协议

## 目标和边界

本文定义后端重构后的异步任务协议，覆盖导入解析、OA 同步、文件处理、read model 重建和搜索索引更新。

核心原则：

- PostgreSQL 是 outbox、任务状态、attempt 和 dead letter 的最终事实源。
- 业务事实、审计事件和 outbox 事件必须在同一个 PostgreSQL 事务提交。
- NATS JetStream 只负责持久投递、ack、重放和消费隔离，不保存最终任务事实。
- Redis 只可用于缓存、限流或短期进度广播，不可作为任务最终状态。
- Python Worker 只执行解析、同步读取和异步计算，不绕过 Axum/API 定义的业务一致性边界。
- OA Mongo 是只读源。Worker 不写 OA 源库，不备份或迁移 OA 源库。

## 组件职责

| 组件 | 职责 | 禁止事项 |
| --- | --- | --- |
| Axum API | 校验请求、执行业务事务、写核心事实、写 `audit.events`、写 `job.outbox_events` 和必要的 `job.worker_tasks` 初始记录。 | 不在请求路径执行长时间文件解析、OA 全量扫描、read model 全量重建。 |
| Outbox publisher | 从 PostgreSQL 读取待发布 outbox，发布到 JetStream，收到 publish ack 后标记已发布。 | 不解释业务 payload，不直接改核心业务事实。 |
| NATS JetStream | 提供 stream、consumer、ack、retry、backoff、重放和消费组隔离。 | 不作为任务查询事实源。 |
| Python Worker | 消费任务消息，读取 MinIO/S3、OA Mongo 只读源和 PostgreSQL，写 staging/结果表、任务状态、attempt、read model。 | 不直接写核销关系等高风险业务事实，除非通过明确服务命令或数据库过程边界。 |
| PostgreSQL | 保存 outbox、任务、attempt、dead letter、worker heartbeat 和最终结果。 | 不把可重建缓存伪装成事实源。 |

## PostgreSQL Outbox 事件模型

建议表：`job.outbox_events`。

```sql
create table job.outbox_events (
  id uuid primary key,
  aggregate_type text not null,
  aggregate_id uuid not null,
  event_type text not null,
  subject text not null,
  payload jsonb not null,
  status text not null,
  idempotency_key text not null,
  trace_id text,
  created_by uuid,
  available_at timestamptz not null default now(),
  locked_by text,
  locked_at timestamptz,
  published_at timestamptz,
  attempt_count integer not null default 0,
  last_error_code text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint outbox_status_chk check (
    status in ('pending', 'publishing', 'published', 'retrying', 'failed', 'dead_lettered', 'cancelled')
  )
);

create unique index outbox_events_idempotency_key_uidx
  on job.outbox_events (idempotency_key);

create index outbox_events_pending_idx
  on job.outbox_events (status, available_at, created_at)
  where status in ('pending', 'retrying');

create index outbox_events_aggregate_idx
  on job.outbox_events (aggregate_type, aggregate_id, created_at);
```

字段约定：

- `event_type` 使用过去式领域事件或明确命令，例如 `import.file_uploaded`、`import.batch_confirmed`、`oa.sync_requested`、`read_model.rebuild_requested`、`search.index_requested`。
- `subject` 是要发布到 JetStream 的 subject，必须可由 `event_type` 稳定推导，但落表保存，避免发布端猜测。
- `payload` 只放任务所需的 ID、scope、版本和对象存储 key，不放原始文件内容、密钥、token 或大块二进制。
- `idempotency_key` 是跨 API、outbox、NATS、Worker 的去重键。推荐格式：`{event_type}:{aggregate_type}:{aggregate_id}:{scope}:{source_version}`。
- `available_at` 用于延迟投递和重试退避。
- `attempt_count` 只记录发布 outbox 到 NATS 的尝试次数，不等同于 Worker 执行次数。

写入规则：

1. 业务事务先锁定并验证核心事实。
2. 同一事务写核心事实、`audit.events`、必要的 `job.worker_tasks` 初始记录和 `job.outbox_events`。
3. 事务提交后由 publisher 投递。若 publisher 崩溃，`pending/retrying` 事件仍可恢复。
4. publisher 使用 `select ... for update skip locked` 批量领取，设置 `publishing`、`locked_by`、`locked_at`。
5. JetStream publish ack 成功后，标记 `published` 和 `published_at`。
6. 发布失败时写 `last_error_code/last_error`，按退避更新 `available_at` 并置为 `retrying`；超过阈值后置为 `dead_lettered` 并写 `job.dead_letters`。

## 任务事实表

建议表：`job.worker_tasks`、`job.worker_attempts`、`job.dead_letters`、`job.worker_heartbeats`。

`job.worker_tasks` 保存用户和系统可查询的任务事实：

```sql
create table job.worker_tasks (
  id uuid primary key,
  task_type text not null,
  status text not null,
  phase text not null,
  idempotency_key text not null,
  owner_user_id uuid,
  visibility text not null default 'owner',
  label text not null,
  source jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  result_summary jsonb not null default '{}'::jsonb,
  affected_scopes text[] not null default '{}',
  affected_months date[] not null default '{}',
  current_count integer not null default 0,
  total_count integer not null default 0,
  percent integer not null default 0,
  error_code text,
  error_summary text,
  retryable boolean not null default true,
  max_attempts integer not null default 5,
  next_attempt_at timestamptz,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  cancelled_at timestamptz,
  constraint worker_task_status_chk check (
    status in ('queued', 'running', 'succeeded', 'failed', 'retrying', 'dead_lettered', 'cancelled')
  ),
  constraint worker_task_visibility_chk check (visibility in ('owner', 'system'))
);

create unique index worker_tasks_idempotency_key_uidx
  on job.worker_tasks (idempotency_key);

create index worker_tasks_owner_status_idx
  on job.worker_tasks (owner_user_id, status, updated_at desc);

create index worker_tasks_active_idx
  on job.worker_tasks (status, next_attempt_at, created_at)
  where status in ('queued', 'retrying', 'running');
```

状态语义：

| 状态 | 含义 | 允许后继 |
| --- | --- | --- |
| `queued` | PostgreSQL 已记录任务，消息等待投递或等待消费。 | `running`、`cancelled`、`dead_lettered` |
| `running` | Worker 已领取并开始处理，最近 heartbeat 未超时。 | `succeeded`、`retrying`、`failed`、`dead_lettered`、`cancelled` |
| `succeeded` | 任务完成，结果已提交 PostgreSQL。 | 无；人工重放必须创建新 idempotency key 或显式 supersede。 |
| `failed` | 不可重试失败，或业务校验失败。 | 人工重放 |
| `retrying` | 可重试失败，等待下一次投递。 | `running`、`dead_lettered`、`cancelled` |
| `dead_lettered` | 超过重试次数、消息无法解码或环境依赖长期不可用。 | 人工重放 |
| `cancelled` | 用户或系统在执行前取消；运行中任务只做协作式取消。 | 无 |

迁移说明：当前 Python `BackgroundJobService` 的 `partial_success`、`acknowledged`、`superseded` 是 UI 层状态。目标模型中，部分成功使用 `status='succeeded'` 加 `result_summary.partial_success=true` 或 `status='failed'` 加明确错误码；已读/替代关系由前端通知表或 `superseded_by_task_id` 扩展字段承载，不进入核心状态机。

`job.worker_attempts` 保存每次执行尝试：

```sql
create table job.worker_attempts (
  id uuid primary key,
  task_id uuid not null references job.worker_tasks(id),
  attempt_no integer not null,
  worker_id text not null,
  nats_stream text,
  nats_consumer text,
  nats_sequence bigint,
  started_at timestamptz not null default now(),
  heartbeat_at timestamptz,
  finished_at timestamptz,
  status text not null,
  error_code text,
  error_summary text,
  error_detail jsonb not null default '{}'::jsonb,
  constraint worker_attempt_status_chk check (
    status in ('running', 'succeeded', 'failed', 'retrying', 'dead_lettered', 'cancelled')
  )
);

create unique index worker_attempts_task_attempt_uidx
  on job.worker_attempts (task_id, attempt_no);
```

`job.dead_letters` 保存无法自动恢复的事件或任务：

```sql
create table job.dead_letters (
  id uuid primary key,
  source_kind text not null,
  source_id uuid not null,
  subject text,
  task_type text,
  idempotency_key text,
  payload jsonb not null,
  error_code text not null,
  error_summary text not null,
  error_detail jsonb not null default '{}'::jsonb,
  replay_status text not null default 'open',
  replayed_by uuid,
  replayed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint dead_letter_source_kind_chk check (source_kind in ('outbox', 'worker_task', 'nats_message')),
  constraint dead_letter_replay_status_chk check (replay_status in ('open', 'replayed', 'ignored'))
);
```

## NATS JetStream 设计

Stream 命名：

| Stream | Subjects | 用途 | 保留策略 |
| --- | --- | --- | --- |
| `FINOPS_EVENTS` | `finops.events.>` | 领域事件广播，供 read model、搜索、审计外部投影订阅。 | 按时间和大小保留，满足重放窗口。 |
| `FINOPS_JOBS` | `finops.jobs.>` | Worker 命令任务，导入解析、OA 同步、read model 重建、搜索索引更新。 | work queue 或 interest policy，消息持久化。 |
| `FINOPS_DLQ` | `finops.dlq.>` | 自动重试耗尽后的运维通知副本。最终事实仍在 PostgreSQL `job.dead_letters`。 | 长保留，低流量。 |

Subject 命名：

| Subject | 任务类型 |
| --- | --- |
| `finops.jobs.import.parse` | 文件解析预览或 staging 解析。 |
| `finops.jobs.import.confirm_postprocess` | 导入确认后的 read model/search/统计后处理。 |
| `finops.jobs.oa.sync` | OA Mongo 只读增量或指定范围同步。 |
| `finops.jobs.files.process` | 附件抽取、OCR、checksum 校验、格式探测。 |
| `finops.jobs.read_model.rebuild` | 工作台、成本、税金等 read model 重建。 |
| `finops.jobs.search.index` | `search_index_rows` 增量更新或重建。 |
| `finops.events.domain` | 业务事实变更事件。 |

Consumer 建议：

| Durable consumer | Stream | Filter subject | Ack 策略 |
| --- | --- | --- | --- |
| `import-parser-workers` | `FINOPS_JOBS` | `finops.jobs.import.*` | explicit ack，`max_ack_pending` 按 worker 并发限制。 |
| `oa-sync-workers` | `FINOPS_JOBS` | `finops.jobs.oa.sync` | explicit ack，低并发，保护 OA 只读源。 |
| `file-workers` | `FINOPS_JOBS` | `finops.jobs.files.*` | explicit ack，可按 CPU/OCR 能力限流。 |
| `read-model-workers` | `FINOPS_JOBS` | `finops.jobs.read_model.*` | explicit ack，同一 scope 串行。 |
| `search-index-workers` | `FINOPS_JOBS` | `finops.jobs.search.*` | explicit ack，可批量 upsert。 |

Retry 和 dead-letter：

- JetStream consumer 使用 `AckWait`、`BackOff`、`MaxDeliver` 控制消息重投。
- Worker 发现可重试错误时写 `worker_attempts`、更新 `worker_tasks.status='retrying'` 和 `next_attempt_at`，然后 `nak` 或延迟重新投递。
- Worker 发现不可重试错误时写 `failed` 并 `ack`，避免无限重投。
- 超过 `max_attempts`、payload schema 不兼容、对象存储文件缺失、OA 源长期不可用等情况写 `dead_lettered` 和 `job.dead_letters`，同时发布 `finops.dlq.{task_type}` 运维通知副本。
- JetStream 没有替代 PostgreSQL dead letter 表的职责。即使 NATS 消息被清理，`job.dead_letters` 仍能人工审计和重放。

## Worker 消息协议

所有消息使用 JSON，顶层字段固定：

```json
{
  "schema_version": "finops.worker_task.v1",
  "message_id": "uuid",
  "task_id": "uuid",
  "task_type": "read_model.rebuild",
  "idempotency_key": "read_model.rebuild:workbench:2026-05:source-v42",
  "trace_id": "trace-id",
  "created_at": "2026-05-16T10:00:00Z",
  "requested_by": "user-uuid-or-system",
  "source": {
    "aggregate_type": "import_batch",
    "aggregate_id": "uuid",
    "event_id": "uuid"
  },
  "scope": {
    "months": ["2026-05"],
    "scope_keys": ["workbench:2026-05"]
  },
  "payload": {},
  "retry": {
    "attempt": 1,
    "max_attempts": 5
  }
}
```

通用约束：

- `schema_version` 必须校验；不支持版本进入 dead letter，不做猜测兼容。
- `message_id` 等于 outbox event id 或 publisher 生成的稳定 UUID，用作 JetStream `Nats-Msg-Id` 去重。
- `task_id` 必须能在 `job.worker_tasks` 查到。查不到时 Worker 不新建业务任务，写 dead letter。
- `idempotency_key` 必须和 `job.worker_tasks.idempotency_key` 一致。
- Worker 每次开始前按 `task_id` 和 `attempt_no` 写 `worker_attempts`，并用事务或 advisory lock 保证同一任务只有一个有效执行者。
- Worker 输出只写 PostgreSQL staging、结果表、read model 表或任务表；不把结果写 Redis 作为事实。

## 任务类型

### 文件解析 `import.parse`

输入：

```json
{
  "session_id": "uuid",
  "import_file_id": "uuid",
  "file_object_id": "uuid",
  "storage_key": "imports/2026/05/file.xlsx",
  "checksum": "sha256",
  "template_code_override": "invoice_export",
  "batch_type_override": "input_invoice",
  "selected_bank_mapping_id": "uuid"
}
```

输出：

- 写 `staging.import_parse_results` 和 `staging.import_parse_issues`。
- 更新 `app.import_files.status`、行数、错误数、模板识别结果和 checksum 校验结果。
- 更新 `job.worker_tasks.result_summary`。
- 解析成功不直接写正式银行流水或发票事实；正式入账仍由确认导入事务完成。

幂等键：

- `import.parse:{import_file_id}:{checksum}:{template_code_override}:{batch_type_override}`。

### OA 同步 `oa.sync`

输入：

```json
{
  "sync_run_id": "uuid",
  "mode": "incremental",
  "watermark_id": "oa-main",
  "from_source_updated_at": "2026-05-16T00:00:00Z",
  "to_source_updated_at": "2026-05-16T10:00:00Z",
  "months": ["2026-05"],
  "row_ids": []
}
```

输出：

- 只读 OA Mongo，归一化写入 `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`。
- 更新 `app.oa_sync_runs`、`app.oa_sync_watermarks`。
- 写后续 outbox：`read_model.rebuild_requested`、`search.index_requested`。

幂等键：

- `oa.sync:{watermark_id}:{mode}:{from}:{to}:{hash(months,row_ids)}`。

边界：

- Worker 不写 OA 源库。
- OA Mongo 不可用时，已存在 read model 可继续服务，`oa_sync_lag_seconds` 和任务失败指标必须告警。

### Read model 重建 `read_model.rebuild`

输入：

```json
{
  "model": "workbench",
  "scope_keys": ["workbench:2026-05"],
  "months": ["2026-05"],
  "reason": "import.batch_confirmed",
  "source_versions": {
    "fact_version": "42",
    "case_snapshot_version": "sha256"
  },
  "force": false
}
```

输出：

- 重建对应 read model 表。
- 更新 `read_model.read_model_rebuild_runs` 或对应模型 metadata 的 `generated_at/source_versions/stale_reason`。
- 必要时继续投递 `search.index_requested`。

幂等键：

- `read_model.rebuild:{model}:{scope_key}:{hash(source_versions)}:{reason}`。

约束：

- 单月 scope 优先；`all` 汇总后台增量聚合，不能阻塞单月查询。
- 同一 `model + scope_key` 同时只能有一个 running 任务。

### 搜索索引 `search.index`

输入：

```json
{
  "mode": "upsert",
  "entity_type": "bank_transaction",
  "entity_ids": ["uuid"],
  "scope_months": ["2026-05"],
  "reason": "import.batch_confirmed"
}
```

输出：

- upsert 或 delete `read_model.search_index_rows`。
- 更新索引任务统计：新增、更新、删除、跳过数量。

幂等键：

- `search.index:{mode}:{entity_type}:{hash(entity_ids)}:{hash(source_versions)}`。

## Publisher 恢复和人工重放

Publisher 恢复策略：

- 启动时扫描 `status in ('publishing') and locked_at < now() - interval '2 minutes'`，回置 `retrying`。
- 每批领取数量有上限，例如 100 条。
- publish 使用 JetStream `Nats-Msg-Id = outbox_events.id`，避免 publisher 崩溃后重复发布造成重复消费。
- 标记 `published` 必须在 publish ack 之后。

人工重放：

- 重放 dead letter 必须创建新的 outbox event 或 worker task，保留原 `dead_letters.id`、原 payload、操作者和原因。
- 重放成功后更新 `dead_letters.replay_status='replayed'`。
- 不允许直接把旧 `dead_lettered` 任务改回 `queued` 而不生成新的 attempt/audit 记录。

## 监控指标

Prometheus 指标建议：

| 指标 | 类型 | 标签 | 含义 |
| --- | --- | --- | --- |
| `finops_outbox_pending_total` | gauge | `event_type` | 等待发布的 outbox 数量。 |
| `finops_outbox_oldest_pending_seconds` | gauge | `event_type` | 最老待发布事件年龄。 |
| `finops_outbox_publish_attempts_total` | counter | `event_type,result` | outbox 发布尝试。 |
| `finops_outbox_dead_letters_total` | counter | `event_type,error_code` | outbox 进入 dead letter 次数。 |
| `finops_worker_tasks_total` | counter | `task_type,status` | 任务状态流转计数。 |
| `finops_worker_task_duration_seconds` | histogram | `task_type,result` | 任务耗时。 |
| `finops_worker_attempts_total` | counter | `task_type,result,error_code` | Worker attempt 结果。 |
| `finops_worker_heartbeat_age_seconds` | gauge | `worker_id,task_type` | Worker 心跳年龄。 |
| `finops_nats_consumer_lag_messages` | gauge | `stream,consumer` | JetStream consumer backlog。 |
| `finops_nats_redeliveries_total` | counter | `stream,consumer,subject` | NATS 重投次数。 |
| `finops_oa_sync_lag_seconds` | gauge | `watermark_id` | OA 同步滞后。 |
| `finops_dead_letters_open_total` | gauge | `source_kind,task_type` | 未处理 dead letter 数。 |

告警底线：

- 任一核心 `event_type` 的 `oldest_pending_seconds` 超过 5 分钟。
- `dead_letters_open_total` 大于 0 且持续 10 分钟。
- OA 同步滞后超过业务阈值。
- read model 重建任务连续失败。
- Worker heartbeat 超时但任务仍为 `running`。

## 实施顺序

1. 建 `job` schema、outbox、worker task、attempt、dead letter、heartbeat 表。
2. 在 Axum 写事务中接入 outbox 写入和任务初始记录。
3. 实现 outbox publisher，先支持 `read_model.rebuild` 和 `search.index`。
4. 接入 JetStream stream、consumer、publish ack、retry/backoff。
5. Python Worker 实现统一消息 envelope、状态更新和 attempt 记录。
6. 将导入解析、OA 同步、read model 重建、搜索索引逐步迁入该协议。
