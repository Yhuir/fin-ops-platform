# RabbitMQ All Runtime Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the remaining runtime event families (`search`, `pending_invoice`, `cost_statistics`, `tax_offset`, `oa.sync`, `file_object.gridfs_migration`) toward production RabbitMQ delivery with independent queues, DLQs, worker envs, metrics, and rollback.

**Architecture:** PostgreSQL remains the source of truth; RabbitMQ remains a wakeup/transport layer. Dispatcher publishes small outbox envelopes to routing keys derived from event type. Consumers read only their own queue(s), then claim/ack/fail PostgreSQL events before RabbitMQ ack/nack.

**Tech Stack:** Python, PostgreSQL outbox, RabbitMQ/pika, systemd, pytest, deployment docs under `deploy/oa` and `docs/operations`.

---

## Final Codex Prompt

```text
/goal 生产级把剩余后台事件族逐步接入 RabbitMQ：为 search.read_model.refresh、pending_invoice.read_model.refresh、cost_statistics.read_model.refresh、tax_offset.read_model.refresh、oa.sync、file_object.gridfs_migration 设计并实现独立 topology/routing/DLQ、dispatcher/consumer 配置、systemd/env 模板、监控和回滚路径，先完成代码与 staging/本地验证，再按可回滚灰度原则执行生产切换。

执行要求：
1. 阅读 AGENTS.md、README/ARCHITECTURE/docs/operations 与现有 RabbitMQ runtime 代码。
2. 不让 RabbitMQ 成为业务事实源；所有 worker 仍必须回 PostgreSQL claim/ack/fail。
3. 为每个事件族定义独立 queue、routing key、DLQ，并保留 least-privilege 用户边界。
4. Dispatcher 默认可发布所有已支持事件，但生产 env 必须能用 RABBITMQ_DISPATCH_EVENT_TYPES 控制灰度范围。
5. Consumer 支持按 worker event types 订阅一个或多个队列；不能把其他事件混进 workbench queue。
6. 监控输出 per-queue/per-DLQ 指标和聚合指标。
7. systemd/env 模板覆盖 dispatcher、topology、workbench、search/pending、cost/tax、oa-sync、file migration worker。
8. staging preflight 必须检查完整 topology、dispatcher shadow check、每类 consumer check。
9. 生产切换必须逐事件族灰度：先 topology apply，再 dispatcher allowlist 扩展，再停旧 polling worker、启新 RabbitMQ worker、触发受控事件验证，失败可反向回滚。
10. 运行相关 pytest、真实 staging preflight（有环境变量时）、git diff --check；记录结果和未完成的生产切换范围。
```

## Files

- Modify: `backend/src/fin_ops_platform/services/runtime_queue.py`
- Modify: `backend/src/fin_ops_platform/services/rabbitmq_runtime.py`
- Modify: `backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Modify: `backend/src/fin_ops_platform/tools/run_rabbitmq_staging_preflight.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_monitoring.py`
- Modify: `tests/test_runtime_queue.py`
- Modify: `tests/test_rabbitmq_runtime.py`
- Modify: `tests/test_rabbitmq_staging_preflight.py`
- Modify: `tests/test_runtime_monitoring.py`
- Modify/Create: `deploy/oa/env/*.example`
- Modify/Create: `deploy/oa/systemd/*.example`
- Modify: `docs/operations/runtime-read-model-hardening.md`
- Modify: `docs/operations/deployment.md`

## Tasks

### Task 1: Multi-event RabbitMQ topology and routing

- [ ] Add a supported event spec table with event type, queue, routing key, DLQ.
- [ ] Make `RabbitMqTopologyManager.plan/apply` declare all supported specs.
- [ ] Make `RabbitMqPublisher` route by event spec, fail fast for unsupported event type.
- [ ] Update tests for all queues and routing keys.

### Task 2: Multi-queue consumer and metrics

- [ ] Make `RabbitMqConsumer.consume_forever` subscribe to queues derived from worker event types.
- [ ] Keep PostgreSQL claim/ack/fail semantics unchanged.
- [ ] Make management metrics return per-queue/per-DLQ metrics and aggregate depth/unacked/consumer/DLQ count.
- [ ] Update tests for multi-queue consumption and metrics aggregation.

### Task 3: Dispatcher/preflight defaults

- [ ] Default dispatch event types to the full supported set in code, but keep env override.
- [ ] Update dispatcher `--check` output to include queue plan.
- [ ] Update staging preflight to check all target consumers without starting long-running workers.
- [ ] Update tests.

### Task 4: Deployment templates and runbook

- [ ] Add env examples for search-pending, cost-tax, oa-sync, file-migration RabbitMQ workers.
- [ ] Update dispatcher env example to list all supported event types for full mode.
- [ ] Update docs with phased rollout and rollback per event family.
- [ ] Keep production switching manual and explicit.

### Task 5: Verification

- [ ] Run targeted pytest for RabbitMQ/runtime/preflight/monitoring.
- [ ] Run `git diff --check`.
- [ ] If staging env exists, run `run_rabbitmq_staging_preflight --json`.
- [ ] Do not switch remaining production workers until topology and checks pass.

