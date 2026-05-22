# RabbitMQ Full Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成生产级 RabbitMQ 接入，让 RabbitMQ 只负责 outbox envelope 投递和 worker 唤醒，PostgreSQL 继续保存所有任务事实、失败事实和可恢复状态。

**Architecture:** PostgreSQL `job.outbox_events` 仍是 durable queue 和业务事实源；新增 publish 状态字段记录 RabbitMQ 投递事实。独立 dispatcher 读取 PostgreSQL envelope 并在 publisher confirm 后标记 published；RabbitMQ consumer 收到消息后必须回 PostgreSQL `event_id` claim，再执行现有 read model handler，最后按 PostgreSQL ack/fail 结果确认 RabbitMQ delivery。

**Tech Stack:** Python 同步 worker、PostgreSQL/psycopg、RabbitMQ AMQP、`pika` BlockingConnection、现有 unittest/pytest 测试。

**Status:** 已执行。RabbitMQ broker 集成测试需要 `RABBITMQ_TEST_URL`，当前环境未配置真实 broker；本地完成单元、契约、CLI check、migration discovery、broader runtime regression 和 diff 检查。

---

### Task 1: PostgreSQL Publish State

**Files:**
- Create: `backend/src/fin_ops_platform/postgres/migrations/0017_rabbitmq_outbox_publish_state.sql`
- Modify: `tests/test_postgres_migrations.py`
- Modify: `tests/postgres_test_utils.py`
- Modify: `tests/test_runtime_infrastructure_postgres_integration.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_queue.py`
- Test: `tests/test_runtime_queue.py`

- [x] Add `publish_status`, `published_at`, `publish_attempt_count`, `publish_last_error`, `next_publish_at`, `publish_locked_by`, `publish_locked_at`, `rabbitmq_exchange`, `rabbitmq_routing_key`, `rabbitmq_message_id`, `publish_confirmed_at` to `job.outbox_events`.
- [x] Add check constraint `publish_status in ('unpublished', 'publishing', 'published', 'failed')`.
- [x] Add claim index for RabbitMQ dispatcher on `publish_status`, `next_publish_at`, `available_at`, `status`, `priority`.
- [x] Extend `job.runtime_outbox_envelope_v1` to expose publish fields for audit/debug.
- [x] Add repository methods `claim_publishable_events`, `mark_published`, `mark_publish_failed`, `reset_publish_state`, `get_event`, and `claim_event_by_id`.
- [x] Update retry/requeue paths so retryable PostgreSQL failures are republishable only after `available_at`.
- [x] Run `PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_postgres_migrations.py -q`.

### Task 2: RabbitMQ Topology and Transport

**Files:**
- Create: `backend/src/fin_ops_platform/services/rabbitmq_runtime.py`
- Create: `tests/test_rabbitmq_runtime.py`
- Create: `tests/test_rabbitmq_integration.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/src/fin_ops_platform/services/runtime_queue.py`

- [x] Add pinned `pika` dependency.
- [x] Extend `RuntimeQueueSettings` with exchange, routing key, DLX, DLQ, heartbeat, blocked timeout, management URL and shadow publish settings.
- [x] Implement envelope validation that rejects wrong schema version, missing event id, and oversized/forbidden payload keys.
- [x] Implement topology manager that declares durable exchange, durable queue, DLX/DLQ and binding only when an explicit topology CLI calls it.
- [x] Implement `RabbitMqPublisher` with persistent JSON messages, `message_id=event_id`, `mandatory=True`, and publisher confirms.
- [x] Run `PYTHONPATH=backend/src python3 -m pytest tests/test_rabbitmq_runtime.py tests/test_runtime_queue.py -q`.

### Task 3: Dispatcher and Consumer Runtime

**Files:**
- Create: `backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py`
- Create: `backend/src/fin_ops_platform/app/rabbitmq_topology.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_worker.py`
- Test: `tests/test_runtime_worker.py`
- Test: `tests/test_rabbitmq_runtime.py`

- [x] Add dispatcher CLI with `--check`, `--batch-size`, `--max-iterations`, `--shadow-publish`, lock timeout and poll interval options.
- [x] Dispatcher must claim publishable PostgreSQL events, publish RabbitMQ envelopes, mark published only after confirm, and mark failed with backoff on publish exceptions.
- [x] Add topology CLI with explicit `--apply` guard; default `--check` only prints planned topology.
- [x] Add RabbitMQ consumer mode to worker when `FIN_OPS_QUEUE_BACKEND=rabbitmq`; PostgreSQL mode remains rollback default.
- [x] Refactor `RuntimeWorker` so RabbitMQ consumer can process an already-claimed PostgreSQL event and only acknowledge RabbitMQ after PostgreSQL ack/fail succeeds.
- [x] Run `PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_worker.py tests/test_rabbitmq_runtime.py -q`.

### Task 4: Monitoring and Operations

**Files:**
- Create: `backend/src/fin_ops_platform/tools/runtime_queue_ops.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_monitoring.py`
- Modify: `tests/test_runtime_monitoring.py`
- Create: `tests/test_runtime_queue_ops.py`
- Modify: `docs/dev/runtime-infrastructure.md`
- Modify: `docs/operations/runtime-read-model-hardening.md`
- Modify: `docs/operations/monitoring.md`
- Modify: `docs/dev/backend.md`
- Modify: `backend/README.md`
- Modify: `deploy/oa/fin_ops.env.example`

- [x] Add health metrics for unpublished/failed publish backlog, dispatcher lag and publish status counts.
- [x] Add optional RabbitMQ Management API metrics for queue depth, unacked messages, consumer count, DLQ count and broker metric errors.
- [x] Add ops CLI subcommands: `inspect`, `requeue`, `republish`, `replay-unpublished --dry-run|--execute`, `pause-dispatcher`, `resume-dispatcher`, `pause-consumer`, `resume-consumer`.
- [x] Document topology, config, shadow publish, consumer enablement, rollback to PostgreSQL polling and production cutover sequence.
- [x] Run `PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_monitoring.py tests/test_runtime_queue_ops.py -q`.

### Task 5: Verification

**Files:**
- All changed files.

- [x] Run targeted backend suite:

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_runtime_queue.py \
  tests/test_runtime_worker.py \
  tests/test_runtime_monitoring.py \
  tests/test_rabbitmq_runtime.py \
  tests/test_runtime_queue_ops.py \
  tests/test_rabbitmq_integration.py \
  tests/test_postgres_migrations.py \
  tests/test_runtime_infrastructure_postgres_integration.py \
  -q
```

- [x] If `RABBITMQ_TEST_URL` exists, run RabbitMQ integration tests; otherwise report they were skipped by configuration.
- [x] Run `git diff --check`.
- [x] Update this plan with final verification status before final response.
