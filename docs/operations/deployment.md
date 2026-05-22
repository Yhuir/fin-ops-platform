# 部署

## 推荐路径

当前推荐 OA 同域部署：

- 前端：`/fin-ops/`
- 后端：`/fin-ops-api/`

详细步骤见 `../../deploy/oa/README.md`。

## 发布前检查

- 后端基础检查通过。
- 前端构建通过。
- PostgreSQL migration 已应用，API 使用 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 与 `FIN_OPS_APP_READ_BACKEND=postgres`。
- Redis 和 MinIO/S3 按目标环境配置；Redis 不可用时 worker 仍必须能通过 PostgreSQL polling 运行。
- OA Mongo 只作为 `oa.sync` worker 的只读外部源；App Mongo 只允许迁移、shadow-read、audit 和 rollback 工具使用。
- OA 菜单和角色 SQL 已按账户类型准备。
- 有可回滚的后端、前端和配置版本。

## Worker 进程矩阵

生产环境按职责拆分 worker 进程，所有进程都连接同一个 PostgreSQL durable queue。不要用 API in-process thread 作为生产刷新机制。

| 进程 | 推荐事件类型 | 启动参数 |
| --- | --- | --- |
| `worker-oa-sync` | `oa.sync` | `--enable-oa-sync --event-type oa.sync` |
| `worker-workbench` | `workbench.read_model.refresh` | `--enable-workbench-read-model-refresh --event-type workbench.read_model.refresh` |
| `worker-search` | `search.read_model.refresh` | `--enable-search-read-model-refresh --event-type search.read_model.refresh` |
| `worker-pending-invoice` | `pending_invoice.read_model.refresh` | `--enable-pending-invoice-read-model-refresh --event-type pending_invoice.read_model.refresh` |
| `worker-cost-tax` | `cost_statistics.read_model.refresh`, `tax_offset.read_model.refresh` | `--enable-cost-statistics-read-model-refresh --enable-tax-offset-read-model-refresh --event-type cost_statistics.read_model.refresh --event-type tax_offset.read_model.refresh` |
| `worker-file-migration` | `file_object.gridfs_migration` | `--enable-file-object-migration --event-type file_object.gridfs_migration` |

可复制的 systemd/env 模板位于：

- `deploy/oa/systemd/fin-ops.service.example`
- `deploy/oa/systemd/fin-ops-worker@.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-topology.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example`
- `deploy/oa/env/fin-ops.common.env.example`
- `deploy/oa/env/fin-ops.secrets.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-*.env.example`

生产 secret 只能放在 `/etc/fin-ops/*.env` 这类 root-only `EnvironmentFile` 中。`RABBITMQ_URL`、`FIN_OPS_POSTGRES_DATABASE_URL`、Redis、MinIO/S3、OA role sync 密码都不能写入 systemd inline `Environment=` 或仓库文件。

示例：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker \
  --worker-id worker-workbench-1 \
  --enable-workbench-read-model-refresh \
  --event-type workbench.read_model.refresh \
  --poll-interval-seconds 2 \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30
```

`--check` 应在发布前对每类 worker 跑一次，确认 handler、PostgreSQL 和 Redis 状态：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker \
  --enable-workbench-read-model-refresh \
  --enable-search-read-model-refresh \
  --enable-pending-invoice-read-model-refresh \
  --enable-cost-statistics-read-model-refresh \
  --enable-tax-offset-read-model-refresh \
  --check
```

## Worker 运行边界

- read model refresh worker 使用 SQL-native projection builder，不构造完整 `Application`，也不调用 `StateStore.load()`。
- `all` scope 只展开为 month/entity shard 子任务；不在单个 worker 事件中做全量同步构建。
- `job.outbox_events` 和 `job.read_model_dirty_scopes` 是权威恢复点；Redis 只用于短 TTL cache、唤醒和辅助锁。
- worker 可水平扩容；PostgreSQL claim 使用 row lock 语义，重复任务通过 dedupe key 和 scope 状态合并。
- 每个 worker 事件都必须设置 `--task-timeout-seconds` 和 `--statement-timeout-seconds`，并通过 `--lock-timeout-seconds` 释放 crash 或卡死后遗留的 `processing` 事件。
- 失败任务必须保留 `last_error` 并进入 retry 或 failed 状态，不能静默 fallback 到旧 snapshot、App Mongo 或 GridFS。

## RabbitMQ 生产切换边界

RabbitMQ 是 outbox envelope transport，不是业务事实源。生产切换必须按以下顺序：

1. 应用 PostgreSQL migration，确认 `job.outbox_events` 已有 publish 状态字段，`job.runtime_outbox_envelope_v1` 可读。
2. 用 `fin-ops-rabbitmq-topology.service` 或同等 one-shot 命令显式创建 durable topology。
3. 保持 PostgreSQL polling worker 运行，启动 `fin-ops-rabbitmq-dispatcher.service` 的 shadow publish 模式；用 `RABBITMQ_DISPATCH_EVENT_TYPES` 控制灰度事件族。
4. 观察 outbox unpublished backlog、publish failed backlog、dispatcher lag、RabbitMQ per-queue depth、DLQ count。
5. 按 worker 族逐个切到 `FIN_OPS_QUEUE_BACKEND=rabbitmq`：workbench、search/pending、cost/tax、oa-sync、file-migration。
6. 每切一组都要触发受控事件验证 PostgreSQL publish/ack 与 RabbitMQ queue/DLQ，再扩 worker 数量和 prefetch。

回滚路径是停止 dispatcher 和 RabbitMQ consumer worker，恢复 worker env 为 `FIN_OPS_QUEUE_BACKEND=postgres`，再启动 PostgreSQL polling worker。详细 runbook 见 `docs/operations/runtime-read-model-hardening.md`。

## 全量 Backfill / Drain

发布 PostgreSQL read model 或 OA projection 变更后，先补结构化 OA 子表并 enqueue 缺失 scope，再由独立 worker drain：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
set +a

/opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py \
  --backfill-oa-children \
  --enqueue-missing \
  --json

/opt/miniconda3/bin/python3 scripts/backfill-runtime-read-models.py \
  --run-worker \
  --max-iterations 200 \
  --lock-timeout-seconds 30 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --json
```

如果上一次 worker 异常退出留下 `processing` 事件，确认没有同名 worker 仍在运行后，可临时把 `--lock-timeout-seconds` 降到 `1` 重新 drain。这个操作只回收超过 lock timeout 的 PostgreSQL queue 事件，不读取旧 snapshot fallback。

## 发布后检查

- `/health`。
- `/api/session/me`。
- 只读/全操作/管理员/不可见账户分层。
- 工作台、导入、税金、成本统计、银行明细、设置页。
- App health 状态和后台任务。
- `job.outbox_events` pending/failed、`job.read_model_dirty_scopes` pending/failed/stale 数量在预期范围内。
