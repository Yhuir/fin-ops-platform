# Runtime Workers Spec-first E2E Spec

Runtime worker 的 Spec-first E2E 目标是证明后台执行面不会让用户看到半同步、假 fresh、卡死队列或缺 worker 的页面状态。本模块不替代 read model 业务 spec；它保护 durable queue、worker registry、RabbitMQ transport、readiness 和 App Health 运行面。

## Spec IDs

| Spec ID | 用户/运维可观察合同 | 必须证明 |
| --- | --- | --- |
| `WORKER-E2E-001` | required workers 全部注册、启动、heartbeat 新鲜，并和 manifest/systemd/env 一致。 | worker registry、deploy manifest、App Health/runtime snapshot 一致。 |
| `WORKER-E2E-002` | durable queue event 从 pending/processing 到 done/failed/dead-letter 的状态流转可观测且可恢复。 | Postgres queue 是事实源；RabbitMQ 只是 wakeup/transport。 |
| `WORKER-E2E-003` | read model refresh handler 只能通过规范 scope 执行，不能写非法 scope 或伪造 readiness fresh。 | scope policy、dirty/outbox、readiness reporter 和 handler guard 一致。 |
| `WORKER-E2E-004` | 依赖 read model 未 fresh 时 worker 应短延迟 defer，不进入长时间 failure/dead-letter 放大。 | dependency-not-fresh defer、superseded resolution 和 active scope dedupe 正确。 |
| `WORKER-E2E-005` | RabbitMQ transport 下 publish/consume 必须先锁定 Postgres event，再 ack message。 | broker envelope 不携带业务 payload；claim 成功后 ack。 |
| `WORKER-E2E-006` | 生产/staging runtime health gate 能证明 queue backlog、failed jobs、stale dirty scope、missing/stale required worker 为 0。 | `runtime_sync_closure_gate` runtime_health pass。 |
| `WORKER-E2E-007` | 长时间运行和真实 systemd/RabbitMQ/Redis/Postgres worker drain 可通过 staging/runtime smoke 证明。 | 本地 mock 不能替代真实服务。 |

## 失败与恢复场景

- worker kind/event type mismatch：App Health 必须暴露 mismatch。
- handler exception：进入 retry 或 dead-letter，不吞错。
- stale processing：可由 ops 命令 guarded release/requeue。
- covered dead-letter：必须有 later done/fresh 或 operator proof 才能 resolve。
- RabbitMQ 不可用：Postgres durable queue 仍保留事实，不能丢业务事件。

## 外部风险

真实 systemd、RabbitMQ broker、Redis、PostgreSQL migration 和长时间 worker drain 属 `external-risk`；必须由 staging/production smoke 证明，不能写成本地 CI covered。
