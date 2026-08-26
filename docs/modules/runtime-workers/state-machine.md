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

### `oa.sync(operation=refresh_attachments)` 分支

- `pending -> processing` 前，request owner 已把 row IDs 限定为 canonical completed 或 `in_progress + expense_claim`；worker 必须对 source 返回的 exact row ID、唯一性和 enqueue-time month scope 再次 fail closed 校验。
- processing 对 selected rows 集合式下载/解析并定向 owner commit，不执行 all/month stale deletion。
- completed rows 才能进入正式发票 promotion，并以 `ensure_matching=true` 补发 matching reconciliation。
- `in_progress + expense_claim` 只允许附件解析结果落到当前 OA/子付款项，promotion、matching 与统一发票池写入必须为零；进行中支付申请及未知表单/状态失败。
- terminal result 只报告该 event 的逐 row 计数与 completed 子集的 promotion summary；不能把旧 projection、普通搜索或另一 row 的结果包装为 done。

## 非法状态

- required instance 集合不是精确 4 个，或未知旧 worker/env/timer 仍 enabled/running。
- registration/handler claim 未登记 event type，或不同 registry 维护第二份 event matrix。
- worker import HTTP/Application 层，或跨 owner 写 canonical facts。
- 新 `%.read_model.refresh` event、`read_model_key` registration、projection/readiness/dirty-scope runtime 出现。
- import/OA worker 回写全量旧 snapshot，或半提交后标记 succeeded。
- OA 精确刷新把 `in_progress + expense_claim` 提前 promotion/匹配/正式导入，或把不支持的进行中表单标记 done。

## 发布与恢复

Deploy 先停止/禁用 registry 外实例和已知 RabbitMQ 遗留 unit/env，再确认 4 个 required workers heartbeat、通用 outbox/领域队列的 PostgreSQL backlog/dead-letter 和 System Audit。Migration `0149_remove_read_model_runtime.sql` forward-only 删除旧 projection schema/dirty-scope。历史 outbox RabbitMQ 列只在上一版本回滚窗口内作为 schema 兼容面保留；当前 API、Worker、监控和部署链路均不读写这些列。物理删列必须晚于回滚窗口并作为独立 schema maintenance 执行，不能与本次运行时切换绑定。
