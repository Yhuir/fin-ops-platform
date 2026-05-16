# Outbox Publisher 07A 实现说明

本文记录 P2-07A PostgreSQL outbox publisher 的实现边界。本阶段不配置 NATS，不实现 Python Worker，不解释业务 payload，不直接写核心业务事实，不访问 OA 源数据库。

## 代码入口

```text
rust/fin-ops-api/crates/fin-ops-api/src/jobs/outbox_publisher.rs
```

核心类型：

| 类型 | 职责 |
| --- | --- |
| `OutboxPublisher` | 执行一轮 claim -> publish -> ack/failure 状态回写。 |
| `OutboxRepository` | 抽象 PostgreSQL outbox 状态变更，便于测试和替换。 |
| `SqlxOutboxRepository` | 基于 `job.outbox_events` 和 `job.dead_letters` 的 SQLx 实现。 |
| `EventPublisher` | 抽象消息发布端；后续 NATS JetStream adapter 只需实现该 trait。 |
| `OutboxPublishSummary` | 一轮执行的指标摘要。 |

## 状态流

```text
pending/retrying
  |
  | claim_batch: update ... set status='publishing', locked_by, locked_at, attempt_count + 1
  v
publishing
  |
  | publish ack
  v
published
```

失败流：

```text
publishing
  |
  | retryable failure 且 attempt_count < max_publish_attempts
  v
retrying

publishing
  |
  | non-retryable failure 或 attempt_count >= max_publish_attempts
  v
dead_lettered + job.dead_letters
```

`claim_batch` 使用 `select ... for update skip locked` 选择 `status in ('pending', 'retrying') and available_at <= now()` 的事件，再原子更新为 `publishing`。该 publisher 不读取或解释 payload 内部字段，只把 outbox 已落表的 `subject` 和 `payload` 交给 `EventPublisher`。

## SQL 写入范围

允许写入：

- `job.outbox_events.status`
- `job.outbox_events.locked_by`
- `job.outbox_events.locked_at`
- `job.outbox_events.published_at`
- `job.outbox_events.attempt_count`
- `job.outbox_events.last_error_code`
- `job.outbox_events.last_error`
- `job.outbox_events.available_at`
- `job.dead_letters`

禁止写入：

- `app.*` 核心业务事实表。
- `read_model.*`。
- `staging.*`。
- OA 源库或任何 Mongo 源库。

## 错误处理

| 场景 | 处理 |
| --- | --- |
| claim SQL 失败 | `publish_once` 返回 repository error，不发布任何消息。 |
| 发布成功但标记 published 失败 | `failed_to_record += 1`；事件仍在数据库中保留现场，后续由运维处理 publishing 超时回收策略。 |
| 可重试发布失败 | 写 `status='retrying'`，记录 `last_error_code/last_error`，按 `retry_backoff_seconds` 推迟 `available_at`。 |
| 不可重试发布失败 | 写 `status='dead_lettered'`，同时插入 `job.dead_letters`。 |
| 重试次数耗尽 | 即使错误本身 retryable，也写 `dead_lettered` 和 `job.dead_letters`。 |
| dead letter 写入失败 | `failed_to_record += 1`；不吞掉状态，summary 暴露异常记录失败。 |

`job.dead_letters.payload` 保存 outbox 原始 payload，`error_detail` 只放 publisher 运行上下文，例如 `publisher_id`、`event_type`、`aggregate_type`、`aggregate_id` 和 `attempt_count`，不补充业务解释。

## 指标

当前模块返回 `OutboxPublishSummary`，可直接映射为后续 Prometheus 指标：

| 字段 | 建议指标 |
| --- | --- |
| `claimed` | `outbox_publisher_claimed_total` |
| `published` | `outbox_publisher_published_total` |
| `retrying` | `outbox_publisher_retrying_total` |
| `dead_lettered` | `outbox_publisher_dead_lettered_total` |
| `failed_to_record` | `outbox_publisher_state_record_failures_total` |

后续接入运行循环时建议补充：

- 每轮 `publish_once` duration histogram。
- claim batch size histogram。
- publish adapter latency histogram。
- 当前 `publishing` 超时数量 gauge。
- pending/retrying backlog gauge。

## 07A 暂不做事项

- 不实现 NATS JetStream 连接、stream、consumer 或 ack 配置。
- 不实现 Python Worker。
- 不定义业务任务 payload schema。
- 不实现 publishing 超时回收任务；当前只保留 `locked_by/locked_at` 和 SQL index 供后续 07B/运维任务处理。
- 不新增 API route。
