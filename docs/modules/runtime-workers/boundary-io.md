# Runtime Worker 模块边界与 I/O

日期：2026-08-15

## 当前集合

`runtime_worker_registry.py` 是唯一 registry，生产必须且只能运行四个 instance：

| Instance | Worker kind | 输入 | 责任 |
| --- | --- | --- | --- |
| `oa-sync` | `oa-sync` | `oa.sync` | OA integration 普通 month/all 同步，以及显式 `operation=refresh_attachments` 的 selected-row 精确附件重解析；后者只接纳 completed 或 `in_progress + expense_claim`，且不执行 stale snapshot deletion |
| `workbench-matching` | `workbench-matching` | PostgreSQL matching dirty scopes | 正式关系候选计算 |
| `import` | `import-job` | `import.process.requested` | 文件导入后台处理 |
| `settings-maintenance` | `settings-maintenance` | settings maintenance events | 数据重置与关系要求重算 |

不存在 read-model worker。未登记的 systemd worker 必须由 release helper stop/disable。

## 输入 I/O

- Event worker 只从 PostgreSQL durable queue claim；不经过第二套 broker/wakeup transport。
- Matching worker 只读写其领域 dirty-scope repository，不使用通用 projection scope；执行正式关系命令时以
  `fin_ops_worker` 对 `app.workbench_idempotency_records` 持有 `SELECT/INSERT/UPDATE`，不得授予 `DELETE`。
- Matching worker 的银行有效分类由 formal-relation fact repository 对计划 IDs 一次批量读取 canonical SQL 分类投影；worker 不装载 category snapshot，不组装 Python effective-category provider。
- 每个 job/event 必须有 bounded retry、lease、idempotency 和结构化失败证据。
- API route 只 enqueue 已登记任务；worker 不读取 HTTP cookie/header，不构造 response，不依赖 `Application`。
- OA 精确附件刷新复用 `oa.sync`，不新增 event/worker；worker 独占 Mongo 下载、OCR 与定向 owner commit。completed 子集才调用 promotion 与 matching reconciliation；`in_progress + expense_claim` 只提交附件解析结果，必须零 promotion/matching/统一发票池写入。API 只读取受控 durable status/result，不得恢复同步 fallback。
- `oa.sync(operation=refresh_attachments)` 的 pending/processing/failed 状态由专用 event status 接口和通用队列指标观测，不得计入全量 `oa_projection` freshness、App Health 全局 OA 状态或发布 readiness；单条修复失败不能污染全量 OA 健康结论。

## 输出 I/O

- 业务结果通过明确 service/repository 写 canonical tables。
- 通用状态写 `job.outbox_events`、background job、attempt 与 heartbeat。
- Worker 不读写 Redis，不写页面 DTO、projection schema、page cache 或 freshness/readiness 状态。

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

Deploy helper 会保留已有实例的吞吐、lease、timeout 与 poll 调优，但在 registration check 之前原子迁移
per-worker env：`FIN_OPS_QUEUE_BACKEND` 固定为 `postgres`，删除该实例遗留的 `FIN_OPS_RABBITMQ_*` 与
`FIN_OPS_REDIS_*` 覆盖。公共 API cache 环境不属于此迁移范围。

## 验证

- Registry/command/health：`tests/test_runtime_worker_registry.py`、`tests/test_runtime_worker.py`。
- Queue/retry/idempotency：`tests/test_runtime_queue.py` 与业务 service tests。
- Deploy exact set：`tests/test_deploy_runtime_examples.py`、`tests/test_read_model_runtime_removal.py`。
- Production：`/health/ready`、worker heartbeat、PostgreSQL queue backlog/dead-letter、runtime closure gate。

Migration `0151_workbench_matching_worker_idempotency_grant.sql` 修复历史只读授权，确保 dirty scope 重试可通过
正式关系命令的持久化幂等边界完成；禁止通过直写 relation 或删除失败 scope 绕过该合同。
