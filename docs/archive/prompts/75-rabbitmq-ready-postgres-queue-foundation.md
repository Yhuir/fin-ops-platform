# 75 RabbitMQ-ready PostgreSQL Queue Foundation

## /goal

实现 RabbitMQ-ready 的生产级 PostgreSQL outbox/dirty-scope 队列基础：固定 PostgreSQL 事实源、统一 read model refresh envelope、幂等 worker 语义、queue 抽象默认 postgres、监控指标、失败/DLQ 策略和未来 RabbitMQ 配置边界，并完成相关测试与文档。

## 背景

当前应用已经有优化后的 read model、worker 和 Redis，但 RabbitMQ 未来只能作为投递通道，不能成为业务状态或事实源。所有刷新任务必须先在 PostgreSQL 中有持久记录。RabbitMQ 消息最多只携带 `event_id/scope_key/source_version` 等 envelope 字段，worker 收到后必须回 PostgreSQL 读取真实任务。

## 并行任务

### A. Schema / Migration Explorer

只读核对 `job.outbox_events`、`job.read_model_dirty_scopes`、`job.runtime_worker_heartbeats` 的字段、状态约束、索引和迁移测试。输出最小 migration 设计，必须覆盖 `source_version`、`priority`、`trace_id`、`schema_version`、`dead_lettered`、dedupe predicate 和 envelope view。

### B. Worker Idempotency Explorer

只读核对 `runtime_queue.py`、`runtime_worker.py`、`workbench_read_model_refresh.py`、`postgres_repositories/read_models.py` 的幂等语义。重点判断重复 event、旧 source_version、多 worker 同 scope、崩溃恢复和 read model overwrite guard。

### C. Monitoring / Docs Explorer

只读核对 `runtime_monitoring.py`、`runtime_redis.py`、`server.py`、`worker.py` 和 `docs/dev`、`docs/operations`。输出已有/缺失指标与文档更新点。

## 串行执行

1. 写失败测试：
   - `RuntimeQueueEvent.to_envelope()` 不包含大 payload。
   - read model refresh enqueue 将 `source_version/priority/trace_id/schema_version` 写入 outbox。
   - dedupe 只对 pending 生效，processing 期间可产生新 pending event。
   - `complete_read_model_refresh(... source_version=...)` 只完成不新于当前事件的 dirty scope。
   - `fail_event` 支持指数退避、最大次数、`dead_lettered`；`requeue_event` 可人工恢复。
   - monitoring 输出 backlog、dirty scopes、oldest pending age、worker lag、duration、失败率。
2. 实现 migration `0016_runtime_outbox_envelope_fields.sql`：
   - 新增 outbox envelope 字段和约束。
   - 将 status check 扩为 `pending|processing|done|failed|dead_lettered`。
   - 将 `(tenant_id, dedupe_key)` partial unique 改为仅 pending。
   - 建 `job.runtime_outbox_envelope_v1` view。
3. 实现代码：
   - 扩展 `RuntimeQueueEvent`、`RuntimeQueueSettings`、`RuntimeQueueRepository`。
   - worker 使用 `ack_event/fail_event`，写 duration，指数退避，max attempts。
   - Workbench dirty scope completion 加 `source_version` guard。
   - Redis helper 记录 hit/miss。
   - worker check/readiness 暴露 queue backend 配置。
4. 更新文档：
   - `docs/dev/runtime-infrastructure.md`
   - `docs/dev/backend.md`
   - `docs/operations/runtime-read-model-hardening.md`
   - `docs/operations/monitoring.md`
5. 验证：
   - `PYTHONPATH=backend/src python -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_monitoring.py tests/test_postgres_migrations.py tests/test_runtime_infrastructure_postgres_integration.py tests/test_workbench_sql_runtime.py -q`
   - `git diff --check`

## 禁止事项

- 不接 RabbitMQ broker。
- 不把 RabbitMQ 作为事实源。
- 不在 RabbitMQ envelope 放页面 snapshot、read model JSON payload 或业务事实。
- 不在 API 请求路径同步重建 read model。
