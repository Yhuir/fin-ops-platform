# Runtime Worker 与 Canonical Read 生产治理

日期：2026-08-15

## 管理边界

- PostgreSQL 是 App canonical facts、durable queue、background job 和 worker heartbeat 的事实源。
- 页面 API 直接查询 canonical facts；没有 page projection、freshness queue 或 cache worker。
- PostgreSQL durable queue/domain table 同时承担任务持久化、claim、retry 与完成状态，不再经过 RabbitMQ 双传输。
- systemd 只运行 registry 的四个 instance：`oa-sync`、`workbench-matching`、`import`、
  `settings-maintenance`。
- `finops-deploy-control` 和 `finops-ensure-runtime-workers` 是生产部署控制面；不要手写第二份 worker 清单。
- Worker helper 在启动检查前原子规范化既有 per-worker env：保留业务吞吐参数，队列固定为 PostgreSQL，
  删除遗留 RabbitMQ/Redis 覆盖；发现 env 是符号链接时 fail closed。

## 运行检查

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --json
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --json
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate --profile stability --json
```

生产 token 只通过 `scripts/with-production-admin-token.sh` 加载，不写入命令历史、日志、evidence 或仓库。

## 页面读取与性能

- 每个组合页面在一个短 `REPEATABLE READ READ ONLY` snapshot 内返回 rows/summary/facets/statistics。
- GET 不 enqueue、不轮询、不访问 Worker queue/Redis；写后最多一次 normal canonical GET。
- canonical repository 使用 set-based SQL、bounded pagination 和 batch hydration，禁止 N+1。
- 核心生产 GET 默认要求 p95 <= 1000ms、p99 <= 2000ms，同时要求 2xx、正确 JSON shape、无 HTML/error fallback。
- 性能失败先看 endpoint 的 DB duration、connection acquire、query count 和 SQL execute/fetch；有证据后再加索引或改 SQL。

## Queue 与 worker

- Durable event 采用 at-least-once；handler 必须幂等。
- processing lease 只在过期后接管；瞬时失败按 bounded retry 回到 pending，达到上限进入明确终态。
- `job.outbox_events` 的 pending/processing/failed、dead-letter 和 required worker missing/stale/mismatch 都是发布 blocker。
- Workbench matching scope 是领域状态，只由 matching repository/orchestrator 管理，不得塞进通用 queue adapter。
- `workbench-matching` 复用正式关系命令，因此生产 `fin_ops_worker` 必须能 `SELECT/INSERT/UPDATE`
  `app.workbench_idempotency_records`；Migration `0151` 是该权限的事实源，不授予 `DELETE`。
- `oa-sync` 同时消费 `oa.sync` 与 `oa.payment_status.reconcile`。后者由 relation 事务登记、按最新 active OA+outflow topology 收敛外部状态；Migration `0158` 提供 App ownership state 和历史 active relation 事件回填，不直接修改外部支付表。Migration `0159` 为生产 worker 共用的 `fin_ops_app_runtime` 补齐 ownership 表的最小 `SELECT/INSERT/UPDATE` 权限；不授予 `DELETE`。
- Runtime queue retention 只清理已完成历史；不得删除 pending、processing、failed 或 dead-lettered 行来伪造健康。

## Read Model 退役治理

Migration `0149_remove_read_model_runtime.sql` 是 forward-only：删除 `job.read_model_dirty_scopes` 和
`read_model` schema，并终止历史 refresh 事件。迁移先检查 schema 只含已知 legacy 对象，发现未知 relation
立即失败；不会删除主数据库或其他业务 schema。

激活候选 release 时必须：

1. 停止 OA sync enqueue timer，再停止 API 和 worker；
2. 执行 migration；
3. 精确删除旧 Workbench generation timer/service/helper 和旧 worker env；
4. stop/disable registry 外 worker；
5. 安装但暂不启动 OA sync enqueue timer，只启动当前四个 worker 与 API；
6. 运行 canonical page audit、HTTP SLO、health/queue/worker closure；
7. T+0/T+30 通过后启动 OA sync enqueue timer；自动回滚同样先验证 previous release，再恢复 timer。

迁移后禁止自动切回依赖旧 schema 的 release。若候选验证失败，保持维护状态，用当前代码向前修复。允许的
read-model 字样仅限历史 migration/checksum 和负向审计；`retired_projection_event_audit` 发现任何新
`%.read_model.refresh` 事件必须失败。

## 发布闭环

自动 release gate 使用两个有界 checkpoint：T+0 与 T+30。每个 checkpoint 必须证明：

- `/health/ready` 成功；
- required worker exact-set、heartbeat 和注册合同正确；
- PostgreSQL outbox backlog/failed/dead-letter 没有恶化；
- canonical page audit 通过；
- HTTP contract 与 p95/p99 达标；
- 可逆临时数据库写验证成功并清理。

业务写 smoke（confirm/withdraw、BankFlow submit/withdraw 等）不是每次自动部署的强制副作用，只在明确的
production scenario 和审批输入下运行；它必须使用测试自有数据并恢复原状态。

## 运维原则

- 修复工具只接受固定参数、dry-run fingerprint、精确计数和显式 operator；不开放任意 SQL/shell。
- 未知 schema、身份歧义、fingerprint 漂移、活动 lease 或不完整恢复证据一律 fail closed。
- 不通过删除 queue 行、伪造 heartbeat、放宽 readiness 或恢复旧 projection 来解阻。
- 本次退役不需要数据库备份。若单独的数据修复创建 task-specific recovery artifact，验证完成后按工具合同删除；
  永远禁止删除主数据库。

## 故障定位顺序

1. `/health/ready` 与 systemd service 状态。
2. 四个 worker heartbeat/registration。
3. PostgreSQL outbox backlog、failed/dead-lettered。
4. endpoint HTTP timing 与 DB timing/query count。
5. canonical page/system audit issue samples。
6. request ID 对应的结构化 error/timing trace。

详细发布命令见 `deploy/oa/README.md`；数据库运行边界见 `docs/operations/postgresql-runtime.md`。
