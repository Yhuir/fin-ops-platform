# Runtime Worker 模块维护入口

- Module key: `runtime-workers`
- 类型: 资源模块
- Route/Page: N/A

## 当前边界

Worker 不依赖 `Application`、`app.server`、`app.auth` 或 HTTP response。当前 registry 精确包含 4 个 required instance：

- `oa-sync`：OA integration mirror/canonical promotion。
- `workbench-matching`：候选匹配领域 dirty-scope 计算；不参与页面 GET。
- `import`：durable import job。
- `settings-maintenance`：数据重置与关系要求重算等受控维护任务。

App read model runtime 已整体退役，不存在 `read_model_key` registration、refresh event、freshness/readiness worker 或 projection owner。PostgreSQL 通用 outbox/attempt/heartbeat、import job 和 Workbench matching dirty scopes 继续作为各自任务事实源；RabbitMQ 只负责可选 wakeup/transport。

页面性能只由 canonical query API 合同衡量：每个核心 probe p95 `<=1000ms`、p99 `<=2000ms`、错误为 0。不得恢复页面 worker/cache/projection 绕过慢查询。

## 修改前必读

- `boundary-io.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/postgresql-runtime.md`

## 代码入口

- `backend/src/fin_ops_platform/services/runtime_queue.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker.py`
- `backend/src/fin_ops_platform/app/worker.py`

## 维护触发器

新增/删除 worker、event type、领域 dirty scope、outbox、heartbeat、systemd/env、queue retry/dead-letter 或 App Health 状态时，同步本模块和运维文档。发现 page refresh/projection/read-model runtime 回归时必须删除，不登记兼容分支。
