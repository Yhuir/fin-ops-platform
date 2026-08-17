# Runtime Workers Spec-first E2E Spec

| Spec ID | 可观察合同 | 必须证明 |
| --- | --- | --- |
| `WORKER-E2E-001` | required workers 精确为 4 个并保持新鲜 heartbeat。 | registry、systemd/env、deploy 与 App Health 一致。 |
| `WORKER-E2E-002` | durable item 的 pending/processing/done/retry/dead-letter 可观测且可恢复。 | PostgreSQL 是状态事实源。 |
| `WORKER-E2E-003` | App read model runtime 保持为 0。 | 无 refresh event/worker/manifest/readiness/projection schema。 |
| `WORKER-E2E-004` | 领域/integration 依赖未满足时有界 defer，不放大 failure。 | retry、superseded 和 shutdown release 正确。 |
| `WORKER-E2E-005` | 四个 Worker 直接从各自 PostgreSQL durable queue/table claim。 | 无 RabbitMQ/Redis 运行时依赖或第二状态机。 |
| `WORKER-E2E-006` | runtime health gate 证明 exact release、queue/DLQ、4 workers、0 legacy event 正常。 | T0 与 T+30 gate 通过。 |
| `WORKER-E2E-007` | 真实 systemd/PostgreSQL 长时间运行可验证。 | 本地 mock 不替代生产 smoke。 |

失败时不得清理有效业务 item 或恢复旧 page worker/transport 来制造通过；forward-only migration 生效后只能向前修复。
