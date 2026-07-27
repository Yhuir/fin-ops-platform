# Runtime Worker 状态机

> 本文件描述当前 worker runtime。已退役页面 projector/refresh worker 和 Workbench
> generation worker 不属于当前状态机。

## Worker Instance 状态

| 状态 | 含义 | 允许流转 |
| --- | --- | --- |
| `starting` | registration/env 已校验，尚未开始 claim | `idle` / `failed` |
| `idle` | 正常轮询，没有可 claim work | `processing` / `stopping` |
| `processing` | 已从 PostgreSQL durable queue claim event/job | `idle` / `deferred` / `failed` |
| `deferred` | 已知依赖或重试条件暂未满足，重新设置 available time | `idle` |
| `failed` | 当前 item 已记录错误/retry/dead-letter | worker 继续处理其它 item；instance fatal 才退出 |
| `stopping` | 收到 stop，停止 claim 新 work | `stopped` |
| `stopped` | 已释放资源并写 heartbeat | 无 |

Worker 不依赖 `Application`、Flask/session/header 或 HTTP response。每个 registration 的
event types、claim scope filter、handler flags 和 statement timeout 都由
`RUNTIME_WORKER_REGISTRY` 派生。

## Durable Queue Item 状态

```text
pending -> processing -> done
                    \-> pending (retry/defer)
                    \-> failed/dead-lettered
```

- `job.outbox_events` 与 `job.read_model_dirty_scopes` 是三个共享 read model refresh 的
  唯一状态事实源。
- RabbitMQ 只发送 wakeup/envelope；consumer 必须回 PostgreSQL claim、ack 和记录失败。
- stale/superseded processing 只能通过受控 queue ops 恢复，不能伪造 done/readiness。
- current-effective pending/processing 覆盖同 scope 历史 failure；未覆盖 failure 保持 blocker。

## 当前 Read Model Worker 集合

带 `read_model_key` 的 registration 必须精确覆盖：

- `workbench_relation`
- `search`
- `no_oa_bank_batch`

三者只接受 `YYYY-MM` 或 `all` scope；`all` 是 fan-out command，不发布可查询 parent
projection。query miss/stale 必须经 `ReadModelRefreshGateway` normalize、validate、
dedupe 后入队。

已退役页面 event/scope/handler/env 不得重新登记。历史 outbox、dirty scope、readiness
和表只作上一版本回滚证据，当前 worker 不 claim。

## 非 Read-Model Worker

- import processing：读取 durable import session/file facts，只写本次 canonical delta。
- OA sync：原子提交 completed/admission/payment-status/watermark canonical snapshot，不
  fan-out 已退役页面 refresh。
- Workbench matching：产生 canonical formal relation plan/facts，不发布页面 projection。
- `bank_flow_rule_batch.canonical_draft.refresh`：幂等维护 canonical batch/event facts，
  不写 read-model readiness/dirty scope。

这些 worker 可被 App Status 观测，但不能出现在 read-model manifest/scope policy 中。

## 非法状态

- registration claim 未登记 event type，或不同 registry 手工复制第二份 event matrix。
- retired page worker/env/systemd instance 仍 enabled/running/failed crash-loop。
- worker 直接 import `Application`/`app.server`/`app.auth`。
- handler 写不属于自身 owner 的 projection、canonical table 或 readiness。
- RabbitMQ publish success 被解释为 job/read-model done。
- import worker 回写全量 state snapshot，或 OA sync 半提交后标记 succeeded。
- `all` fan-out command 被写成 fresh parent readiness。

## 发布与恢复

- deploy preflight 先 stop/disable 当前 registry 未登记的旧 worker instance，再确认 retired
  event/dirty scope 没有 `processing`。
- 门禁失败时保留 import、matching、canonical draft 和三个共享 read-model worker 运行，
  不进入“全部 worker 已停”的半发布状态。
- queue retry、dead-letter repair、history prune 和 worker instance convergence 只通过
  `finops-deploy-control`/登记运维工具执行；prune 只删除 `done` 历史。
- migration `0127_direct_canonical_page_runtime_retirement.sql` 不删除 runtime 状态或历史表。

## 验证入口

- `tests/test_runtime_worker_registry.py`
- `tests/test_runtime_worker.py`
- `tests/test_runtime_queue.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_rabbitmq_runtime.py`
- `tests/test_deploy_runtime_examples.py`
- `tests/test_platform_runtime_boundary_guards.py`
