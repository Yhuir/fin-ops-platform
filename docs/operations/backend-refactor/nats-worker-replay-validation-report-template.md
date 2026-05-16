# NATS Worker Replay Staging 验证报告模板

适用任务：`outbox-worker-07`

边界：本报告只覆盖 staging 验证闭环，不切换生产，不访问 OA 源数据库，不记录 secret、完整 URI、密码、token、S3 credential 或 NATS credential。PostgreSQL 是最终事实源，NATS JetStream 和 DLQ 只作为投递、重投和运维通知机制。

## 基本信息

| 项 | 内容 |
| --- | --- |
| 验证日期 |  |
| 环境 | staging |
| 操作人 |  |
| 变更单/任务 ID | outbox-worker-07 |
| Git commit/branch |  |
| PostgreSQL 连接标识 | 仅写环境名或脱敏别名 |
| NATS 连接标识 | 仅写环境名或脱敏别名 |

## 1. Stream 和 Consumer

| 检查项 | 期望 | 实际 | 结论 |
| --- | --- | --- | --- |
| `FINOPS_EVENTS` stream | 存在，subjects 为 `finops.events.>` |  |  |
| `FINOPS_JOBS` stream | 存在，work queue/explicit ack consumer 可用 |  |  |
| `FINOPS_DLQ` stream | 存在，仅作运维通知副本 |  |  |
| `read-model-workers` consumer | `AckWait/MaxDeliver/BackOff` 与 runbook 一致 |  |  |
| `ops-dlq-watchers` consumer | explicit ack，低重试 |  |  |
| PostgreSQL 对照 | outbox/task/dead letter 状态计数合理 |  |  |

证据摘要：

```text

```

## 2. Outbox Publisher

| 检查项 | 期望 | 实际 | 结论 |
| --- | --- | --- | --- |
| claim batch | `pending/retrying` 置 `publishing`，使用 lock/skip locked |  |  |
| publish ack | JetStream ack 后才置 `published` |  |  |
| message headers | 含 event id、idempotency key、trace id |  |  |
| duplicate guard | 重复 publisher 运行不重复发布已 published 事件 |  |  |
| sensitive payload guard | payload 含敏感字段时不发布，进入可审计失败状态 |  |  |

证据摘要：

```text

```

## 3. Worker Consume、Ack Delay 和 Heartbeat

| 检查项 | 期望 | 实际 | 结论 |
| --- | --- | --- | --- |
| consume message | Worker 成功解析 `finops.worker_task.v1` envelope |  |  |
| load task | 先读取 PostgreSQL `job.worker_tasks` 并校验幂等键 |  |  |
| create attempt | handler 前写 `job.worker_attempts(status='running')` |  |  |
| heartbeat | 同步更新 attempt heartbeat 和 `job.worker_heartbeats` |  |  |
| success ack | PostgreSQL 成功提交后 ack NATS |  |  |
| ack delay | ack delay 小于 consumer `AckWait` |  |  |

证据摘要：

```text

```

## 4. Redelivery、Retry 和 Backoff

| 场景 | 期望 | 实际 | 结论 |
| --- | --- | --- | --- |
| 可重试失败 | task/attempt 置 `retrying`，写 `next_attempt_at` |  |  |
| NATS redelivery | `nak` 或 BackOff 后重投 |  |  |
| 连续失败 | attempt 递增，错误摘要脱敏 |  |  |
| retry exhausted | task/attempt 置 `dead_lettered`，写 `job.dead_letters` |  |  |

证据摘要：

```text

```

## 5. DLQ

| 来源 | 期望 PostgreSQL 状态 | NATS 行为 | 实际 | 结论 |
| --- | --- | --- | --- | --- |
| outbox publish permanent failure | `job.dead_letters.source_kind='outbox'` | 可发 `finops.dlq.outbox` 副本 |  |  |
| worker retry exhausted | `source_kind='worker_task'` | terminal ack 或 DLQ 副本 |  |  |
| invalid NATS message | `source_kind='nats_message'` | terminal ack，避免无限重投 |  |  |

证据摘要：

```text

```

## 6. 人工 Replay

| 检查项 | 期望 | 实际 | 结论 |
| --- | --- | --- | --- |
| list filter | 支持按 `task_id/event_id/source_kind` 查询 open dead letter |  |  |
| worker replay | 新建 worker task 和 outbox event，不原地复活旧任务 |  |  |
| outbox replay | 新建 outbox event，原 dead letter 置 `replayed` |  |  |
| audit | `audit.events` 记录 operator、reason、result、新 id |  |  |
| CLI help | `--help` 不输出 secret 或完整 URI |  |  |

执行命令摘要：

```text

```

## 7. 脱敏检查

| 项 | 检查结果 |
| --- | --- |
| 错误摘要无 password/token/secret/credential |  |
| `error_detail` 无完整 URI、S3 credential、NATS credential |  |
| CLI 输出无 secret |  |
| 报告正文无 secret |  |

## 8. 结论

| 项 | 结果 |
| --- | --- |
| staging 验证是否通过 |  |
| 是否需要回滚 |  |
| 是否影响 read-model thread | 否，除非本次验证显式运行 disposable read model smoke task |
| 遗留风险 |  |
| 后续人工动作 |  |
