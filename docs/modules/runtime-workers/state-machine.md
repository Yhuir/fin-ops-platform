# Runtime Worker 状态机

## Worker Instance

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `starting` | registration/env 已校验 | `idle` / `failed` |
| `idle` | 正常轮询，无可 claim work | `processing` / `stopping` |
| `processing` | 处理已 claim 的领域/integration item | `idle` / `deferred` / `failed` |
| `deferred` | 有界退避后重试 | `idle` |
| `failed` | item 已记录 retry/dead-letter | instance 可继续处理其它 item |
| `stopping` | 停止 claim 并释放当前 item | `stopped` |
| `stopped` | 已释放资源并写 heartbeat | 无 |

## Durable Item

```text
pending -> processing -> done
                    \-> pending (retry/defer)
                    \-> failed/dead-lettered
```

- 通用 runtime event 以 `job.outbox_events` 为事实源；import 与 matching 使用各自 PostgreSQL durable queue/table。
- Worker 直接在 PostgreSQL durable queue 上 claim/complete；不存在 broker publish/ack 的第二状态机。
- stale processing 只能通过受控 queue ops 释放；不能伪造 done。
- App 页面 GET 不 enqueue、不等待这些状态，也不从它们推导财务 payload。

## 非法状态

- required instance 集合不是精确 4 个，或未知旧 worker/env/timer 仍 enabled/running。
- registration/handler claim 未登记 event type，或不同 registry 维护第二份 event matrix。
- worker import HTTP/Application 层，或跨 owner 写 canonical facts。
- 新 `%.read_model.refresh` event、`read_model_key` registration、projection/readiness/dirty-scope runtime 出现。
- import/OA worker 回写全量旧 snapshot，或半提交后标记 succeeded。

## 发布与恢复

Deploy 先停止/禁用 registry 外实例和已知 RabbitMQ 遗留 unit/env，再确认 4 个 required workers heartbeat、通用 outbox/领域队列的 PostgreSQL backlog/dead-letter 和 System Audit。Migration `0149_remove_read_model_runtime.sql` forward-only 删除旧 projection schema/dirty-scope；migration `0150_remove_rabbitmq_transport.sql` forward-only 删除 outbox 的 RabbitMQ 发布列、索引和约束。生效后不回滚到依赖旧 schema 的 release，只能向前修复。
