# NATS JetStream 配置草案 - P2-07B

本文定义 fin-ops 后端重构阶段的 NATS JetStream stream、consumer、retry/backoff、DLQ 和运维检查方案。本阶段只输出配置方案和部署草案，不配置真实 NATS 服务，不写 NATS credential，不实现 Worker，不访问 OA 源数据库。

## 边界

- PostgreSQL `job.outbox_events`、`job.worker_tasks`、`job.worker_attempts` 和 `job.dead_letters` 是最终任务事实源。
- NATS JetStream 只负责消息投递、ack、重投、consumer 隔离和短期重放。
- NATS DLQ 只作为运维通知副本；正式 dead letter 仍必须写 PostgreSQL `job.dead_letters`。
- Worker 的 OA 同步任务只允许通过既有只读逻辑访问 OA 源，不允许写 OA 源库。
- 本文所有 credential 均只用环境变量名表示；真实值必须由部署环境或 secret manager 注入。

## 部署草案

仓库内提供本地/内网草案：

```text
deploy/backend-refactor/nats/docker-compose.nats.yml
deploy/backend-refactor/nats/nats.finops.conf
```

草案默认将 NATS client 和 monitoring 端口绑定到 `127.0.0.1`：

```text
127.0.0.1:4222
127.0.0.1:8222
```

生产部署要求：

1. 不开放公网；如跨主机访问，必须走内网/VPC、SSH tunnel 或服务网格。
2. `NATS_FINOPS_*` 用户名和密码只从受控环境注入，不提交 `.env` 实值。
3. JetStream store 必须放在有备份和容量监控的持久卷。
4. Stream/consumer 初始化命令必须可重复执行，变更前先导出现有配置。
5. 不把 NATS 当任务查询源；API 查询任务状态只查 PostgreSQL。

## Streams

| Stream | Subjects | Retention | Storage | 目标 |
| --- | --- | --- | --- | --- |
| `FINOPS_EVENTS` | `finops.events.>` | `limits` | `file` | 领域事件广播，供 read model、search、审计外部投影订阅。 |
| `FINOPS_JOBS` | `finops.jobs.>` | `workqueue` | `file` | Worker 命令任务，导入解析、OA 同步、文件处理、read model/search 重建。 |
| `FINOPS_DLQ` | `finops.dlq.>` | `limits` | `file` | 运维通知副本；最终事实仍在 PostgreSQL `job.dead_letters`。 |

建议初始化命令：

```bash
nats stream add FINOPS_EVENTS \
  --subjects "finops.events.>" \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 168h \
  --dupe-window 2m

nats stream add FINOPS_JOBS \
  --subjects "finops.jobs.>" \
  --storage file \
  --retention work \
  --discard old \
  --dupe-window 2m

nats stream add FINOPS_DLQ \
  --subjects "finops.dlq.>" \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 720h \
  --dupe-window 2m
```

说明：

- Outbox publisher 发布时应设置 `Nats-Msg-Id = job.outbox_events.id`，利用 JetStream duplicate window 降低重复发布影响。
- `FINOPS_JOBS` 使用 work queue retention，让同一任务只被同一 worker 组领取；任务事实仍由 PostgreSQL 判断幂等和最终状态。
- `FINOPS_EVENTS` 和 `FINOPS_DLQ` 使用 limits retention，便于短期重放和运维排查。

## Subjects

| Subject | 来源 | 消费者 |
| --- | --- | --- |
| `finops.jobs.import.parse` | outbox publisher | `import-parser-workers` |
| `finops.jobs.import.confirm_postprocess` | outbox publisher | `import-parser-workers`、后续 read model/search 消费者 |
| `finops.jobs.oa.sync` | outbox publisher | `oa-sync-workers` |
| `finops.jobs.files.process` | outbox publisher | `file-workers` |
| `finops.jobs.read_model.rebuild` | outbox publisher | `read-model-workers` |
| `finops.jobs.search.index` | outbox publisher | `search-index-workers` |
| `finops.events.domain` | outbox publisher | 领域事件订阅者 |
| `finops.dlq.outbox` | publisher/worker 运维副本 | ops consumer |
| `finops.dlq.worker` | worker 运维副本 | ops consumer |

## Consumers

| Durable | Stream | Filter | AckWait | MaxDeliver | BackOff | MaxAckPending | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `import-parser-workers` | `FINOPS_JOBS` | `finops.jobs.import.*` | `60s` | `8` | `5s,30s,2m,10m,30m,1h,2h` | `50` | 文件解析和导入后处理，可中等并发。 |
| `oa-sync-workers` | `FINOPS_JOBS` | `finops.jobs.oa.sync` | `120s` | `5` | `30s,2m,10m,30m,2h` | `2` | 低并发保护 OA 只读源；不可写 OA 源库。 |
| `file-workers` | `FINOPS_JOBS` | `finops.jobs.files.*` | `300s` | `6` | `30s,2m,10m,30m,2h,6h` | `10` | OCR、checksum、格式探测等可能耗时任务。 |
| `read-model-workers` | `FINOPS_JOBS` | `finops.jobs.read_model.*` | `120s` | `6` | `10s,1m,5m,30m,2h,6h` | `8` | 同一 scope 需要 worker 内部串行或 PostgreSQL advisory lock。 |
| `search-index-workers` | `FINOPS_JOBS` | `finops.jobs.search.*` | `120s` | `6` | `10s,1m,5m,30m,2h,6h` | `20` | 可批量 upsert search index。 |
| `ops-dlq-watchers` | `FINOPS_DLQ` | `finops.dlq.*` | `30s` | `3` | `10s,1m,5m` | `20` | 运维通知；不得替代 PostgreSQL dead letter。 |

建议初始化命令：

```bash
nats consumer add FINOPS_JOBS import-parser-workers \
  --filter "finops.jobs.import.*" \
  --ack explicit \
  --deliver all \
  --replay instant \
  --ack-wait 60s \
  --max-deliver 8 \
  --backoff "5s,30s,2m,10m,30m,1h,2h" \
  --max-pending 50

nats consumer add FINOPS_JOBS oa-sync-workers \
  --filter "finops.jobs.oa.sync" \
  --ack explicit \
  --deliver all \
  --replay instant \
  --ack-wait 120s \
  --max-deliver 5 \
  --backoff "30s,2m,10m,30m,2h" \
  --max-pending 2

nats consumer add FINOPS_JOBS file-workers \
  --filter "finops.jobs.files.*" \
  --ack explicit \
  --deliver all \
  --replay instant \
  --ack-wait 300s \
  --max-deliver 6 \
  --backoff "30s,2m,10m,30m,2h,6h" \
  --max-pending 10

nats consumer add FINOPS_JOBS read-model-workers \
  --filter "finops.jobs.read_model.*" \
  --ack explicit \
  --deliver all \
  --replay instant \
  --ack-wait 120s \
  --max-deliver 6 \
  --backoff "10s,1m,5m,30m,2h,6h" \
  --max-pending 8

nats consumer add FINOPS_JOBS search-index-workers \
  --filter "finops.jobs.search.*" \
  --ack explicit \
  --deliver all \
  --replay instant \
  --ack-wait 120s \
  --max-deliver 6 \
  --backoff "10s,1m,5m,30m,2h,6h" \
  --max-pending 20

nats consumer add FINOPS_DLQ ops-dlq-watchers \
  --filter "finops.dlq.*" \
  --ack explicit \
  --deliver all \
  --replay instant \
  --ack-wait 30s \
  --max-deliver 3 \
  --backoff "10s,1m,5m" \
  --max-pending 20
```

## Ack 和 retry 策略

### Outbox publisher

1. Publisher 从 PostgreSQL `job.outbox_events` claim `pending/retrying`。
2. Publisher 发布到 JetStream，收到 JetStream publish ack 后才把 PostgreSQL outbox 标记为 `published`。
3. Publish 失败时更新 PostgreSQL outbox 为 `retrying`，由 PostgreSQL `available_at` 控制 publisher 级重试。
4. Publish 重试耗尽时写 PostgreSQL `job.dead_letters`，并可向 `finops.dlq.outbox` 发布运维副本。

### Worker consumer

1. Worker 收到消息后先读取 PostgreSQL `job.worker_tasks`，校验 idempotency key 和任务状态。
2. Worker 开始执行前写 `job.worker_attempts`，执行中更新 heartbeat。
3. 成功提交 PostgreSQL 结果后 ack NATS 消息。
4. 可重试失败：写 `worker_attempts` 和 `worker_tasks.status='retrying'`，然后 `nak` 或让 BackOff 重投。
5. 不可重试失败：写 `worker_tasks.status='failed'` 或 `dead_lettered`，写 `job.dead_letters` 后 ack，避免无限重投。
6. Worker 超过 `MaxDeliver` 或 schema 不兼容时，必须先写 PostgreSQL dead letter，再发布 `finops.dlq.worker` 运维副本。

## 失败重放策略

重放以 PostgreSQL 为准，不以 NATS 残留消息为准。

| 场景 | 重放方式 |
| --- | --- |
| outbox publish 失败但未 dead letter | 修复 NATS/网络后等待 `job.outbox_events.available_at` 到期，publisher 自动重试。 |
| outbox 已 dead letter | 运维确认后新建一条 outbox event 或把原 event 复制为新 id/idempotency key；原 dead letter 标记 `replayed`。 |
| worker 可重试失败 | 修复依赖后按 `worker_tasks.next_attempt_at` 或人工调度重新投递同一任务。 |
| worker dead letter | 根据 `job.dead_letters` payload 和 error_detail 生成新任务或新 outbox，不直接修改旧 NATS message。 |
| NATS stream 数据丢失 | 从 PostgreSQL `job.outbox_events` 和任务表重建待投递消息；NATS 不是最终事实源。 |

人工重放前必须记录：

- 变更单或操作人。
- `dead_letters.id`。
- 新 outbox event id 或新 worker task id。
- replay reason。
- replay 后 PostgreSQL 状态和 NATS stream sequence。

## 运维检查命令

基础健康：

```bash
nats server check connection
nats server check jetstream
curl -fsS http://127.0.0.1:8222/healthz
```

Stream 检查：

```bash
nats stream info FINOPS_EVENTS
nats stream info FINOPS_JOBS
nats stream info FINOPS_DLQ
nats stream report
```

Consumer 检查：

```bash
nats consumer info FINOPS_JOBS import-parser-workers
nats consumer info FINOPS_JOBS oa-sync-workers
nats consumer info FINOPS_JOBS file-workers
nats consumer info FINOPS_JOBS read-model-workers
nats consumer info FINOPS_JOBS search-index-workers
nats consumer info FINOPS_DLQ ops-dlq-watchers
```

PostgreSQL 对照检查：

```sql
select status, count(*)
from job.outbox_events
group by status
order by status;

select status, count(*)
from job.worker_tasks
group by status
order by status;

select source_kind, replay_status, count(*)
from job.dead_letters
group by source_kind, replay_status
order by source_kind, replay_status;
```

Lag 和堆积排查：

```bash
nats consumer report FINOPS_JOBS
nats stream info FINOPS_JOBS
```

如果 NATS consumer lag 上升但 PostgreSQL `worker_tasks` 没有对应 running/retrying 变化，优先检查 Worker 是否在线、consumer durable 是否正确、worker 是否能连接 PostgreSQL。不要通过删除 NATS 消息来“修复”任务状态。

## 上线门禁

- [ ] Docker Compose 或目标部署系统已注入 NATS credential，仓库无明文 credential。
- [ ] NATS 只暴露在 localhost、内网或受控隧道。
- [ ] `FINOPS_EVENTS`、`FINOPS_JOBS`、`FINOPS_DLQ` stream 存在且配置符合本文。
- [ ] 6 个 durable consumer 存在且 BackOff/MaxDeliver 与本文一致。
- [ ] PostgreSQL outbox publisher 已能 publish ack 后标记 `published`。
- [ ] Worker 实现前，不能把消息积压误判为任务完成。
- [ ] PostgreSQL `job.dead_letters` 已纳入告警；NATS DLQ 只作为运维副本。

## Staging 验证闭环 - outbox-worker-07

本节用于 staging 验证，不切换生产，不访问 OA 源数据库，不使用真实 secret。所有连接信息只通过受控环境变量注入，记录时只写环境变量名和脱敏后的主机别名。

### 1. Stream 和 Consumer 基线

记录以下命令输出摘要，不粘贴 credential、完整 URI 或 token：

```bash
nats stream info FINOPS_EVENTS
nats stream info FINOPS_JOBS
nats stream info FINOPS_DLQ
nats consumer info FINOPS_JOBS read-model-workers
nats consumer info FINOPS_DLQ ops-dlq-watchers
```

PostgreSQL 对照：

```sql
select status, count(*) from job.outbox_events group by status order by status;
select status, count(*) from job.worker_tasks group by status order by status;
select source_kind, replay_status, count(*) from job.dead_letters group by source_kind, replay_status order by source_kind, replay_status;
```

通过条件：

- `FINOPS_JOBS`、`FINOPS_DLQ` 存在，consumer 使用 explicit ack。
- `AckWait`、`MaxDeliver`、`BackOff` 与本文 consumer 表一致，或记录经批准的 staging 差异。
- PostgreSQL 中没有意外的长期 `publishing`、`running` 或 open dead letter。

### 2. Outbox Publisher 发布和防重复

准备一条 staging disposable `job.outbox_events`，payload 只包含 task id、scope、source event id、idempotency key 和 trace id，不包含 password、token、secret、credential、原始文件内容或完整 URI。

运行：

```bash
cd rust/fin-ops-api
OUTBOX_PUBLISHER_ID=staging-outbox-worker-07 cargo run --bin outbox_publisher -- --once
```

通过条件：

- publisher 使用 `select ... for update skip locked` claim batch，并将 claimed 行置为 `publishing`。
- JetStream publish ack 后，PostgreSQL `job.outbox_events.status='published'` 且 `published_at` 非空。
- NATS message header 包含 `Nats-Msg-Id`、`X-Event-Id`、`X-Idempotency-Key`、`X-Trace-Id`。
- 重复运行不会重复发布已 `published` 的 outbox；崩溃恢复只处理 stale `publishing`。

### 3. Worker Ack Delay 和 Heartbeat

使用 staging disposable task 运行 Python worker smoke handler：

```bash
PYTHONPATH=backend/src python3 scripts/tools/run_worker_task_consumer.py \
  --subject finops.jobs.read_model.rebuild \
  --stream FINOPS_JOBS \
  --durable read-model-workers \
  --smoke-succeed
```

通过条件：

- Worker 消费消息后先读取 `job.worker_tasks`，校验 `task_id/task_type/idempotency_key`。
- handler 前写入 `job.worker_attempts(status='running')`，并将 task 置为 `running`。
- heartbeat 同时更新 `job.worker_attempts.heartbeat_at` 和 upsert `job.worker_heartbeats`。
- PostgreSQL 结果提交后才 ack NATS；ack delay 小于 consumer `AckWait`。

### 4. Redelivery、Retry 和 Backoff

用 disposable task 触发可重试失败，避免访问 OA 源库。检查：

```sql
select status, retryable, next_attempt_at, error_code, error_summary
from job.worker_tasks
where id = '<task_id>';

select attempt_no, status, error_code, error_summary
from job.worker_attempts
where task_id = '<task_id>'
order by attempt_no;
```

通过条件：

- `RetryableWorkerError` 在未耗尽时写 `worker_tasks.status='retrying'` 和 `next_attempt_at`。
- NATS 消息执行 `nak` 或按 BackOff 重投。
- 连续失败达到 `max_attempts` 后进入 `dead_lettered`，写 `job.dead_letters(source_kind='worker_task')`。
- 错误摘要和详情不包含 password、token、secret、credential、完整 URI 或原始文件内容。

### 5. DLQ 和 Terminal Failure

分别验证三类 dead letter：

- outbox publish permanent failure：`job.outbox_events.status='dead_lettered'`，`job.dead_letters.source_kind='outbox'`。
- worker retry exhausted：`job.worker_tasks.status='dead_lettered'`，attempt 记录完整。
- schema invalid 或 task 缺失的 NATS message：`job.dead_letters.source_kind='nats_message'`，消息执行 terminal ack，避免无限重投。

NATS `FINOPS_DLQ` 只记录运维通知副本；最终审计和 replay 依据始终是 PostgreSQL `job.dead_letters`。

### 6. 人工 Replay

先列出 open dead letter：

```bash
python3 scripts/tools/job_dead_letter_replay.py list --source-kind worker_task --limit 20
```

按 task id 或 event id 重放：

```bash
python3 scripts/tools/job_dead_letter_replay.py replay \
  --task-id '<task_uuid>' \
  --operator-id '<operator_uuid>' \
  --reason 'staging retry after dependency restored'

python3 scripts/tools/job_dead_letter_replay.py replay \
  --event-id '<outbox_event_uuid>' \
  --operator-id '<operator_uuid>' \
  --reason 'staging outbox replay after NATS recovery'
```

通过条件：

- replay 不把旧 `dead_lettered` 或 `failed` 任务原地改回 `queued`。
- worker task replay 创建新的 `job.worker_tasks` 和新的 `job.outbox_events`，新 idempotency key 带 replay 后缀。
- outbox replay 创建新的 `job.outbox_events`，原 dead letter 置 `replayed`。
- `audit.events` 记录 operator、reason、source id、新 task/outbox id 和 result。
- CLI `--help` 不输出 secret、完整 URI、密码、token、S3 credential 或 NATS credential。
