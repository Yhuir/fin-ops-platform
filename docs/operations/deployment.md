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

## Release-Based 发布

生产主发布路径是服务器 release，而不是覆盖 `/opt/fin-ops/current/backend`：

```bash
./scripts/deploy-oa.sh
```

默认发布到：

```text
/opt/fin-ops/releases/<release-name>/src
```

发布脚本会生成 `src/RELEASE.json`，并通过 `finops-prod` 免密 SSH 调用服务器上的 root-owned helper：

```bash
sudo -n /usr/local/sbin/finops-deploy-control check-release <release-name>
sudo -n /usr/local/sbin/finops-deploy-control activate <release-name>
```

`activate` 负责让 API、RabbitMQ worker 和 dispatcher 指向该 release 并重启 active services。发布脚本随后会执行
`deploy/oa/bin/finops-ensure-runtime-workers.sh`，幂等安装 runtime worker systemd 模板、补齐缺失的 worker env、并
`enable/restart` 最小生产正确性必须长期运行的 worker 矩阵。最后脚本会检查 live 前端 `index.html` 与 release 内
`web/dist/index.html` 的哈希一致，避免后端和前端版本漂移。

`git push main` 不是部署动作。标准顺序是：本地验证、提交、推送、执行 release 发布、发布后 smoke check。默认脚本会拒绝 dirty worktree；生产发布必须能追溯到具体 commit。

release 目录会占用磁盘。默认保留最近 8 个 release，同时永远保护 deploy-control status 中仍被引用的 active release。旧 root-owned 历史 release 如果当前部署用户没有权限删除，会被跳过并输出原因，需要单独做一次 root 清理。可按磁盘容量调整：

```bash
./scripts/deploy-oa.sh --keep-releases 12
```

旧 `/opt/fin-ops/current/backend` 覆盖式部署只保留为显式兼容模式，不作为生产主路径：

```bash
./scripts/deploy-oa.sh --mode legacy-current --host 139.155.5.132 --user root --reload-nginx
```

## Worker 进程矩阵

生产环境按职责拆分 worker 进程，所有进程都连接同一个 PostgreSQL durable queue。不要用 API in-process thread 作为生产刷新机制。

| 进程 | 推荐事件类型 | 启动参数 |
| --- | --- | --- |
| `worker-oa-sync` | `oa.sync` | `--enable-oa-sync --event-type oa.sync` |
| `worker-workbench` | `workbench.read_model.refresh` | `--enable-workbench-read-model-refresh --event-type workbench.read_model.refresh` |
| `worker-bank-detail` | `bank_detail.read_model.refresh` | `--enable-bank-detail-read-model-refresh --event-type bank_detail.read_model.refresh --max-events-per-iteration 24` |
| `worker-search-pending` | `search.read_model.refresh`, `pending_invoice.read_model.refresh` | `--enable-search-read-model-refresh --enable-pending-invoice-read-model-refresh --event-type search.read_model.refresh --event-type pending_invoice.read_model.refresh` |
| `worker-invoice-usage-collection` | `input_invoice_usage.read_model.refresh`, `output_invoice_collection.read_model.refresh` | `--enable-input-invoice-usage-read-model-refresh --enable-output-invoice-collection-read-model-refresh --event-type input_invoice_usage.read_model.refresh --event-type output_invoice_collection.read_model.refresh` |
| `worker-cost-tax` | `cost_statistics.read_model.refresh`, `tax_offset.read_model.refresh` | `--enable-cost-statistics-read-model-refresh --enable-tax-offset-read-model-refresh --event-type cost_statistics.read_model.refresh --event-type tax_offset.read_model.refresh` |
| `worker-import` | `import.process.requested` | `--enable-import-job-processing --event-type import.process.requested` |
| `worker-workbench-matching` | `job.workbench_matching_dirty_scopes` | `--enable-workbench-matching` |
| `worker-file-migration` | `file_object.gridfs_migration` | 可选迁移 worker；只有 legacy GridFS 与对象存储 secret 已配置时才启用 |

不要部署 `fin-ops-worker@oa-rabbitmq.service` 这类没有匹配 handler 的实例。OA worker 的实例名应指向 `oa.sync`，例如 `fin-ops-worker@oa-sync-rabbitmq.service`，并配置 `--enable-oa-sync --event-type oa.sync`。

可复制的 systemd/env 模板位于：

- `deploy/oa/systemd/fin-ops.service.example`
- `deploy/oa/systemd/fin-ops-worker@.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-topology.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example`
- `deploy/oa/env/fin-ops.common.env.example`
- `deploy/oa/env/fin-ops.secrets.env.example`
- `deploy/oa/env/fin-ops.postgres-migrator.env.example`
- `deploy/oa/env/fin-ops.worker.oa-sync.env.example`
- `deploy/oa/env/fin-ops.worker.workbench.env.example`
- `deploy/oa/env/fin-ops.worker.workbench-matching.env.example`
- `deploy/oa/env/fin-ops.worker.bank-detail.env.example`
- `deploy/oa/env/fin-ops.worker.search-pending.env.example`
- `deploy/oa/env/fin-ops.worker.invoice-usage-collection.env.example`
- `deploy/oa/env/fin-ops.worker.cost-tax.env.example`
- `deploy/oa/env/fin-ops.worker.import.env.example`
- `deploy/oa/env/fin-ops.worker.file-migration.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-*.env.example`

生产 secret 只能放在 `/etc/fin-ops/*.env` 这类 root-only `EnvironmentFile` 中。`RABBITMQ_URL`、`FIN_OPS_POSTGRES_DATABASE_URL`、`FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL`、Redis、MinIO/S3、OA role sync 密码都不能写入 systemd inline `Environment=` 或仓库文件。migrator DSN 应单独放在 `/etc/fin-ops/fin-ops.postgres-migrator.env`，仅在执行 schema migration 时手动加载，不要加入 API/worker unit。

最小生产正确性不需要 RabbitMQ，也不应依赖人工长期手动启动。标准 release 发布会自动运行：

```bash
sudo -n /bin/bash "$RELEASE_DIR/src/deploy/oa/bin/finops-ensure-runtime-workers.sh" "$RELEASE_DIR/src"
```

该脚本只在目标 env 文件缺失时从模板创建，不覆盖已有 secret 或 worker 配置；它会安装/更新
`fin-ops-worker@.service`，并启用、重启：

```bash
fin-ops-worker@oa-sync.service
fin-ops-worker@workbench.service
fin-ops-worker@workbench-matching.service
fin-ops-worker@bank-detail.service
fin-ops-worker@search-pending.service
fin-ops-worker@invoice-usage-collection.service
fin-ops-worker@cost-tax.service
fin-ops-worker@import.service
```

如果需要手动修复一台历史服务器，可以执行等价命令：

```bash
sudo /bin/bash deploy/oa/bin/finops-ensure-runtime-workers.sh "$(pwd)"
```

`--check` 应在发布前对每类 worker 跑一次，确认 handler、PostgreSQL 和 Redis 状态：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker \
  --enable-oa-sync \
  --enable-workbench-read-model-refresh \
  --enable-bank-detail-read-model-refresh \
  --enable-search-read-model-refresh \
  --enable-pending-invoice-read-model-refresh \
  --enable-input-invoice-usage-read-model-refresh \
  --enable-output-invoice-collection-read-model-refresh \
  --enable-cost-statistics-read-model-refresh \
  --enable-tax-offset-read-model-refresh \
  --enable-import-job-processing \
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
5. 按 worker 族逐个切到 `FIN_OPS_QUEUE_BACKEND=rabbitmq`：workbench、search/pending、cost/tax、oa-sync、file-migration、import-job。RabbitMQ consumer 仍会按 heartbeat 间隔低频 drain PostgreSQL durable queue，RabbitMQ 只作为唤醒层。
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
