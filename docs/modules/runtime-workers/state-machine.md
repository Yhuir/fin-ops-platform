# Runtime Worker 状态机

> 修改 `Runtime Worker` 相关业务状态、UI 状态或 worker 状态前必须读取本文件。当前状态以 PostgreSQL durable outbox、worker heartbeat 和 RabbitMQ transport facts 为事实源；legacy page read-model dirty scope/readiness 已下线，不再作为 App Health 或页面读证明。

## 业务状态

Runtime worker 本身不拥有业务实体；它维护真实后台执行事实和投递事实。

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| Outbox event | `pending` | `job.outbox_events.status` | 新建、重试、requeue 后进入；可被 worker claim 为 `processing`。 |
| Outbox event | `processing` | `job.outbox_events.status`、`locked_by`、`locked_at`、`attempts` | worker claim 后进入；handler 成功变 `done`，普通失败变 `pending` / `failed` / `dead_lettered`；依赖 read model 未 fresh 时短延迟 defer 回 `pending`；超过 lock timeout 可被 reclaim。 |
| Outbox event | `done` | `job.outbox_events.status`、`processed_at` | worker complete 后进入；终态，除运维审计外不重放。 |
| Outbox event | `failed` | `job.outbox_events.status`、`last_error` | 非 retryable 或 retry 次数受限时进入；可由受控 requeue 回到 `pending`。 |
| Outbox event | `dead_lettered` | `job.outbox_events.status`、`dead_lettered_at`、`last_error` | 达到 max attempts 后进入；只能通过受控 requeue 或 guarded resolve 处理。 |
| Publish state | `unpublished` / `pending` / `published` / `failed` | `job.outbox_events.publish_*` | dispatcher claim publishable event 后发布；只有 publisher 成功确认后才能 mark published。 |
| Worker heartbeat | `polling` / `processing` / `idle` / `deferred` / `failed` | `job.runtime_worker_heartbeats` | worker loop 上报；App Health 用 heartbeat lag、kind、event types 判定 missing/stale/mismatch。`deferred` 表示当前 outbox event 已短延迟回到 pending，不计为业务成功或普通失败。 |

禁止流转：

- 禁止直接 SQL 把 `failed` / `dead_lettered` 改成 `done`，必须走 `runtime_queue_ops` 并保留 operator reason。
- 禁止把已删除的 legacy dirty scope/readiness 重新包装成 App Health/App Status `fresh` 证明。
- 禁止 RabbitMQ 成为状态事实源；RabbitMQ 只能保存 routing envelope，用于 wakeup/transport。
- 禁止 worker 依赖 `Application`、HTTP response、cookie/header、`app.auth` 或 legacy full snapshot。

## UI 状态

本模块没有独立页面。用户侧状态由 App Health 消费 runtime facts；业务页面读路径应走 direct API，不再消费页面 read model freshness。

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面初次读取 App Health 或 direct API | 还没有 runtime 或业务响应。 |
| empty | direct API 返回空业务结果 | 空业务结果不需要 read model readiness 证明。 |
| error | App Health/runtime snapshot 返回 unavailable、worker failed、dead-letter 或 dependency issue | 展示故障，不把旧 projection 伪装为 fresh。 |
| stale / refreshing | outbox pending/processing、worker stale 或业务 API 自己的 direct loading/error 状态 | 只作为运维诊断；业务页面不再靠页面 read model 状态决定读结果。 |
| permission disabled/hidden | 由各业务 API/auth 决定 | Runtime worker 不处理用户权限；App Health 页面权限由 app shell/API contract 保护。 |

## Worker / Outbox 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `ready` | required workers heartbeat 正常，当前关键 outbox 无 backlog/blocker | 继续监控。 |
| `pending` / `processing` | outbox event 正在等待或执行 | worker 继续处理；必要时用 App Health/ops 定位 lag。 |
| `failed` / `dead_lettered` | handler 失败或超过重试上限 | 运维 inspect/requeue；必要时修复配置、数据或代码。 |
| `unavailable` | DB、worker、RabbitMQ 或 runtime monitoring 不可用 | App Health 定位 dependency；不得伪造 readiness/fresh。 |

依赖未完成的特殊恢复：

- 如果 legacy handler 抛出 `*_read_model_not_fresh` / `read_model_not_fresh`，`RuntimeWorker` 使用 `RuntimeQueueRepository.defer_event(...)` 将 outbox event 放回 `pending`，默认 `available_at=now()+2s`；它不会补投页面 refresh。
- defer 会回滚本次 claim 增加的 `attempts`，不会走 `runtime_failure`、`failed` 或 `dead_lettered`。
- defer 不会把任何 projection/readiness 标为 fresh；它只缩短已知依赖顺序竞态的等待时间。
- App Health 汇总 runtime 状态时必须以 current-effective outbox、worker heartbeat 和 RabbitMQ facts 为准；历史 page read-model generation/readiness failure 不能升级为全局 blocked。

当前触发来源：

- 业务写入同事务写入真实 outbox 或返回 direct affected scopes。
- 导入、OA 同步、文件迁移、外部系统同步、受控修复等真实后台任务写入 outbox。
- 运维工具受控 requeue/backfill 触发。

失败恢复：

1. 先查 App Health 和 `/health.runtime_infrastructure`，定位 worker instance、event type、outbox status 和 last error。
2. 对 dead-letter event 先 `runtime_queue_ops inspect`，确认是否可重放。
3. 对历史页面 read-model 残留，不再恢复 `check-read-model-scope-contracts` 或 readiness/dirty-scope dead-letter resolve；先确认是否属于当前真实 worker registry，再决定 requeue 或记录为 legacy residue。
4. 修复代码/配置/数据后 requeue，等待 worker heartbeat 和 outbox 收敛。
5. legacy read-model dead-letter resolve 仍是删除对象；不得把 readiness/dirty scope resolve 流程恢复成 App Health 证明。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-22 | App Health 聚合 Workbench active repair 时优先 current-effective refreshing/rebuilding，旧 consistency failure 不再写 blocked dependency | 修复“运行摘要显示刷新中但顶部阻断”的矛盾状态；worker/queue 仍按 PostgreSQL durable facts 收敛，不伪造 fresh | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_health_api tests.test_app_status_overview_service tests.test_runtime_monitoring -v` |
| 2026-06-13 | 依赖 read model 未 fresh 使用短延迟 defer | `*_read_model_not_fresh` 不再走 60s 普通 retry/dead-letter，减少跨 read model fan-out 长尾 | `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter -v` |
| 2026-06-16 | `bank_detail:all` 不再由 downstream all-scope dependency defer 自动推导 | 防止 `turnover_ledger:all` / `no_oa_bank_batch:all` 与 `bank_detail:all` fan-out 互相放大，页面长期 refreshing；gateway 后续已删除 | `tests/test_runtime_worker.py`、`tests/test_read_model_architecture_guards.py` |
| 2026-06-13 | 补齐 RabbitMQ transport 下 stale/superseded processing 运维恢复 | RabbitMQ 只负责 wakeup，PostgreSQL `processing` 超过 lock timeout 且没有 envelope 时，可先用 `resolve-superseded-processing` 清理已被更新同 dedupe event 覆盖的旧 processing，再用 `release-stale-processing` 释放仍需重跑的事件；不伪造 readiness/fresh | `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_queue_ops -v` |
| 2026-06-11 | 补齐 runtime worker 状态机 | 明确 outbox、legacy dirty scope 删除清单、heartbeat、deleted readiness、RabbitMQ transport 和 UI 消费语义 | 待本轮 runtime-workers 验证 |
