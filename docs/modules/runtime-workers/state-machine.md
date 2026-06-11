# Runtime Worker 状态机

> 修改 `Runtime Worker` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前状态以 PostgreSQL durable queue、worker heartbeat 和 read model readiness 为事实源。

## 业务状态

Runtime worker 本身不拥有业务实体；它维护后台执行事实和派生数据刷新事实。

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| Outbox event | `pending` | `job.outbox_events.status` | 新建、重试、requeue 后进入；可被 worker claim 为 `processing`。 |
| Outbox event | `processing` | `job.outbox_events.status`、`locked_by`、`locked_at`、`attempts` | worker claim 后进入；handler 成功变 `done`，失败变 `pending` / `failed` / `dead_lettered`；超过 lock timeout 可被 reclaim。 |
| Outbox event | `done` | `job.outbox_events.status`、`processed_at` | worker complete 后进入；终态，除运维审计外不重放。 |
| Outbox event | `failed` | `job.outbox_events.status`、`last_error` | 非 retryable 或 retry 次数受限时进入；可由受控 requeue 回到 `pending`。 |
| Outbox event | `dead_lettered` | `job.outbox_events.status`、`dead_lettered_at`、`last_error` | 达到 max attempts 后进入；只能通过受控 requeue 或 guarded resolve 处理。 |
| Publish state | `unpublished` / `pending` / `published` / `failed` | `job.outbox_events.publish_*` | dispatcher claim publishable event 后发布；只有 publisher 成功确认后才能 mark published。 |
| Dirty scope | `pending` | `job.read_model_dirty_scopes.status` | producer 或 gateway 入队后进入；worker claim 对应 outbox event 后推进。 |
| Dirty scope | `processing` | `job.read_model_dirty_scopes.status` | refresh handler 执行中；成功变 `done`，失败变 `failed`，超时由 queue/worker 恢复。 |
| Dirty scope | `done` | `job.read_model_dirty_scopes.status`、source version | projection 完成且 source version guard 通过后进入。 |
| Dirty scope | `failed` | `job.read_model_dirty_scopes.status`、`last_error` | refresh 失败进入；必须修复后 requeue，不得直接改 fresh。 |
| Worker heartbeat | `polling` / `processing` / `idle` / `failed` | `job.runtime_worker_heartbeats` | worker loop 上报；App Health 用 heartbeat lag、kind、event types 判定 missing/stale/mismatch。 |

禁止流转：

- 禁止直接 SQL 把 `failed` / `dead_lettered` 改成 `done`，必须走 `runtime_queue_ops` 并保留 operator reason。
- 禁止没有真实 projection/readiness 证明时把 dirty scope 或 App Status 标成 `fresh`。
- 禁止 RabbitMQ 成为状态事实源；RabbitMQ 只能保存 routing envelope，用于 wakeup/transport。
- 禁止 worker 依赖 `Application`、HTTP response、cookie/header、`app.auth` 或 legacy full snapshot。

## UI 状态

本模块没有独立页面。用户侧状态由 App Health 和业务页面消费 runtime facts：

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面初次读取 App Health 或业务 read model | 还没有 runtime/read model 响应。 |
| empty | 业务 read model fresh 且 row count 为 0 | 空业务结果允许 green，但必须有 readiness 记录。 |
| error | App Health/runtime snapshot 返回 unavailable、worker failed、dead-letter 或 dependency issue | 展示故障，不把旧 projection 伪装为 fresh。 |
| stale / refreshing | dirty scope pending/processing、source mismatch、schema mismatch、worker stale | 页面可展示旧数据和刷新提示，但必须暴露 stale/refreshing 语义。 |
| permission disabled/hidden | 由各业务 API/auth 决定 | Runtime worker 不处理用户权限；App Health 页面权限由 app shell/API contract 保护。 |

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | `read_model.app_status_readiness` 或对应 active generation 证明当前 schema/source version 可读 | 页面可读取 projection，Redis 才能缓存 payload。 |
| `missing` | registry 中存在 read model，但没有 readiness 证明或 projection 不存在 | query gateway 返回 refreshing/unavailable 并 enqueue refresh。 |
| `refreshing` | dirty scope pending/processing，或父 scope 等待 shard fan-out | App Health yellow；worker 继续处理。 |
| `stale` | dirty scope、source mismatch 或 schema mismatch 表示 projection 落后 | 入队 refresh；页面不能标 fresh。 |
| `failed` | handler/rebuild 失败，或 dirty scope/outbox failed/dead-letter | 运维 inspect/requeue；必要时修复 scope contract 或代码。 |
| `unavailable` | DB、worker、projection、runtime monitoring 不可用 | route 映射错误状态，App Health 定位 dependency。 |

Refresh 触发来源：

- 页面 query gateway 在 missing/stale/mismatch 时触发。
- 业务写入同事务标记 dirty/outbox。
- Derived lifecycle 在导入、ETC、关系、invoice lifecycle 等事件后触发。
- 运维工具受控 requeue/backfill 触发。

失败恢复：

1. 先查 App Health 和 `/health.runtime_infrastructure`，定位 worker instance、event type、dirty scope 和 last error。
2. 对 dead-letter event 先 `runtime_queue_ops inspect`，确认是否可重放。
3. 对 read model scope contract 问题先跑 `scripts/check-read-model-scope-contracts.py --json`，避免重放必然失败的旧 invalid scope。
4. 修复代码/配置/数据后 requeue，等待 worker heartbeat、outbox、dirty scope 和 readiness 收敛。
5. 只有真实 projection/readiness 已 fresh，且无 active dirty scope 时，才能 guarded resolve 已过期 dead-letter。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-11 | 补齐 runtime worker 状态机 | 明确 outbox、dirty scope、heartbeat、readiness、RabbitMQ transport 和 UI 消费语义 | 待本轮 runtime-workers 验证 |
