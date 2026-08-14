# Runtime Worker 模块边界与 I/O

日期：2026-08-15

## 当前集合

`runtime_worker_registry.py` 是唯一 registry，生产必须且只能运行四个 instance：

| Instance | Worker kind | 输入 | 责任 |
| --- | --- | --- | --- |
| `oa-sync` | `oa-sync` | `oa.sync` | OA integration 同步 |
| `workbench-matching` | `workbench-matching` | PostgreSQL matching dirty scopes | 正式关系候选计算 |
| `import` | `import-job` | `import.process.requested` | 文件导入后台处理 |
| `settings-maintenance` | `settings-maintenance` | settings maintenance events | 数据重置与关系要求重算 |

不存在 read-model worker。未登记的 systemd worker 必须由 release helper stop/disable。

## 输入 I/O

- Event worker 只从 PostgreSQL durable queue claim；RabbitMQ 只可作为已登记事件的可选 wakeup/transport。
- Matching worker 只读写其领域 dirty-scope repository，不使用通用 projection scope。
- 每个 job/event 必须有 bounded retry、lease、idempotency 和结构化失败证据。
- API route 只 enqueue 已登记任务；worker 不读取 HTTP cookie/header，不构造 response，不依赖 `Application`。

## 输出 I/O

- 业务结果通过明确 service/repository 写 canonical tables。
- 通用状态写 `job.outbox_events`、background job、attempt 与 heartbeat。
- Worker 不写页面 DTO、projection schema、Redis page cache 或 freshness/readiness 状态。

## 依赖方向

```text
registry -> worker bootstrap -> handler -> domain service -> repository
API route -> application service -> durable queue/domain repository
```

禁止 handler 反向依赖 route/auth/server response；禁止 service 裸 SQL；禁止恢复旧 worker/event/env。

## 文件范围

- Registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- Runner：`backend/src/fin_ops_platform/services/runtime_worker.py`
- Handlers：`backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- Queue：`backend/src/fin_ops_platform/services/runtime_queue.py`
- Matching queue：`backend/src/fin_ops_platform/services/postgres_repositories/workbench_matching_queue.py`
- Deploy helper：`deploy/oa/bin/finops-ensure-runtime-workers.sh`

## 验证

- Registry/command/health：`tests/test_runtime_worker_registry.py`、`tests/test_runtime_worker.py`。
- Queue/retry/idempotency：`tests/test_runtime_queue.py` 与业务 service tests。
- Deploy exact set：`tests/test_deploy_runtime_examples.py`、`tests/test_read_model_runtime_removal.py`。
- Production：`/health/ready`、worker heartbeat、queue backlog/DLQ、runtime closure gate。
