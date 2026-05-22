# RabbitMQ-ready PostgreSQL 队列事实源收敛计划

## Goal

把 read model refresh 队列固定为 PostgreSQL outbox/dirty scopes 事实源，并提前定义 RabbitMQ 只能作为投递通道的边界。当前实现仍默认使用 PostgreSQL queue，不引入 RabbitMQ 运行依赖。

## 验收标准

- `job.outbox_events` 持久记录 envelope 所需字段：`event_id`（由 `id::text` 暴露）、`scope_type`、`scope_key`、`source_version`、`priority`、`status`、`attempt_count`、`last_error`、`available_at`、`locked_by`、`locked_at`、`trace_id`。
- read model refresh envelope 只包含 routing identity 和版本，不携带页面 snapshot 或业务事实 payload。
- processing 中的同一 dedupe key 不阻塞新 pending event，避免刷新中新增版本丢失。
- worker 失败支持指数退避、最大次数、`dead_lettered`、手动 requeue；旧 `source_version` 不把更新的 dirty scope 标记为 done。
- worker ack payload 记录 refresh duration，监控可读取 backlog、dirty scopes、oldest pending age、worker lag、refresh duration、失败率。
- 配置边界包含 `FIN_OPS_QUEUE_BACKEND=postgres|rabbitmq` 和 RabbitMQ 预留项；默认仍为 `postgres`。

## 执行顺序

1. 只读梳理现有 schema、worker、monitoring、docs。
2. 先补失败测试覆盖 envelope、dedupe、DLQ/requeue、source version guard、queue settings 和监控字段。
3. 新增 `0016_runtime_outbox_envelope_fields.sql`，扩展 outbox/dirty scope 字段、约束、索引和 `job.runtime_outbox_envelope_v1` view。
4. 更新 `RuntimeQueueRepository` 和 `RuntimeQueueEvent`，实现统一 envelope、priority、trace、source_version、`ack_event`、`fail_event`、`requeue_event`。
5. 更新 `RuntimeWorker`，实现指数退避、最大尝试次数、duration 写回和 heartbeat trace/source version。
6. 更新 Workbench refresh handler，用 `source_version` guard 完成 dirty scope。
7. 更新 runtime monitoring、Redis hit/miss、本地 worker check 输出。
8. 更新中文开发/运维文档和归档 prompt。
9. 运行相关后端测试、迁移静态检查和 diff check。

## 风险控制

- 不把 RabbitMQ 设为事实源；worker 即使未来收到 RabbitMQ 消息也必须回 PostgreSQL 按 `event_id` 读取真实任务。
- 不在队列消息中放大 JSON、页面 snapshot 或业务事实。
- 迁移仅新增字段、约束、索引和 view；不删除业务数据。
- 保留旧 `attempt_count` / `attempts` 同步语义。
