# Backend

后端是 Python 服务，负责导入解析、OA 接入、关联工作台、核销、台账、税金、ETC、成本统计、设置、后台任务和 app health。

## 目录

```text
backend/src/fin_ops_platform/
  app/       HTTP 入口、路由、OA 鉴权、响应组装
  domain/    领域模型和枚举
  services/  业务服务、适配层、持久化、direct query 和后台任务
```

## 本地检查

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## 本地启动

```bash
./scripts/start-backend.sh
```

脚本默认加载 `.runtime/fin_ops_platform/local-postgres.env`。该文件不入库；本地需要接入服务器 PostgreSQL/MinIO/Redis 时，把 `FIN_OPS_POSTGRES_DATABASE_URL`、`FIN_OPS_REDIS_URL`、对象存储变量和可选 `FIN_OPS_SSH_TUNNEL_*` 写在这里即可。检测到 PostgreSQL URL 后，脚本会自动启用 PostgreSQL storage/read backend。非交互 shell 解析到错误 Python 时，可在该文件中设置 `FIN_OPS_PYTHON_BIN=/path/to/python3`。

本地执行 schema migration 时不要复用 runtime 账号。把 migrator DSN 放在 `.runtime/fin_ops_platform/local-postgres-migrator.env`，只配置 `FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL`，然后执行：

```bash
set -a
source .runtime/fin_ops_platform/local-postgres.env
source .runtime/fin_ops_platform/local-postgres-migrator.env
set +a

PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres apply
```

本地和服务器同构运行时必须先通过：

```bash
./scripts/check-local-runtime.sh --dependencies-only
```

`./scripts/start-backend.sh` 会在 PostgreSQL runtime 下自动执行该检查。后端启动后可用：

```bash
./scripts/check-local-runtime.sh --require-backend
```

确认 `/health`、PostgreSQL、Redis、MinIO/S3、`/api/workbench/summary` 和 `/api/workbench/groups` 都正常。前端首屏使用 split summary/groups 接口；如果本地 `8000` 上还残留旧 `backend.api.main:app` 进程，应停止它并使用 `./scripts/start-backend.sh` 默认的 `8001` 入口。

## 测试

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

## 持久化

- 生产主读写通过 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 和 `FIN_OPS_APP_READ_BACKEND=postgres` 接入 PostgreSQL。
- PostgreSQL 运行时连接使用 `FIN_OPS_POSTGRES_DATABASE_URL` 或 `DATABASE_URL`，生产环境应从 root-only credential file 注入。
- PostgreSQL migration 连接优先使用 `DATABASE_URL`，其次使用专用 `FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL`，最后才回退到 `FIN_OPS_POSTGRES_DATABASE_URL`。
- app Mongo 旧路径仍保留，用于迁移观察期回滚、shadow-read、导出和审计工具。
- OA 数据库保持只读，只能通过 `MongoOAAdapter` 读取，不能作为 app 写库。

## Worker

生产后台任务使用独立 worker 进程，不依赖 API 进程内 thread。worker 通过 PostgreSQL durable queue claim 任务，Redis 只做短 TTL cache 和 wake-up。RabbitMQ 只能作为 envelope 投递通道，不能替代 `job.outbox_events` 事实源：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check
```

常用角色：

- `worker-oa-sync`：`--enable-oa-sync --worker-kind oa-sync --event-type oa.sync`
- `worker-import`：`--enable-import-job-processing --worker-kind import-job --event-type import.process.requested`
- `worker-workbench-matching`：`--enable-workbench-matching --worker-kind workbench-matching`
- `worker-file-migration`：可选迁移 worker，只有 legacy GridFS 与对象存储 secret 已配置时才启用

权威 worker 清单来自 `python -m fin_ops_platform.tools.runtime_worker_manifest`；不要在文档中维护第二份页面 read-model refresh worker 清单。

最小生产正确性先用 PostgreSQL polling worker，不需要 RabbitMQ。标准 release 发布会自动运行服务器
root-owned helper `/usr/local/sbin/finops-ensure-runtime-workers`，确保常驻 worker 矩阵安装、开机自启并重启到当前 release。
仓库内的 `deploy/oa/bin/finops-ensure-runtime-workers.sh` 是 helper 源文件，历史服务器手动修复时先由 root 安装到固定路径再执行：

```bash
sudo install -m 0755 -o root -g root \
  deploy/oa/bin/finops-ensure-runtime-workers.sh \
  /usr/local/sbin/finops-ensure-runtime-workers
sudo /usr/local/sbin/finops-ensure-runtime-workers "$(pwd)"
```

生产或本地补数 worker 必须带明确的卡死释放和 SQL statement timeout，例如：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker \
  --worker-id worker-import-1 \
  --registration import \
  --worker-instance import \
  --poll-interval-seconds 2 \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --max-attempts 5
```

队列配置默认：

```text
FIN_OPS_QUEUE_BACKEND=postgres
RABBITMQ_URL=
RABBITMQ_EXCHANGE=finops.events
RABBITMQ_DEAD_LETTER_EXCHANGE=finops.events.dlx
RABBITMQ_PREFETCH=10
RABBITMQ_PUBLISH_CONFIRM=true
```

RabbitMQ 生产接入需要三个入口：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.rabbitmq_topology --check
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.rabbitmq_topology --apply
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.rabbitmq_dispatcher --check --shadow-publish
```

`rabbitmq_dispatcher` 只发布 `RuntimeQueueEvent.to_envelope()`，并且只在 publisher confirm 后更新 PostgreSQL publish 状态。`FIN_OPS_QUEUE_BACKEND=rabbitmq` 时，`app.worker` 使用 RabbitMQ consumer，但仍回 PostgreSQL claim event；`FIN_OPS_QUEUE_BACKEND=postgres` 是回滚路径。

运行时补数和收敛入口优先使用 direct API、import/OA/file-migration worker 和专用 repair 工具。页面 read-model backfill 脚本不再是生产发布或页面可见性入口。常用 worker 自检：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check --registration import
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check --registration oa-sync
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check --registration workbench-matching
```

## 相关文档

- `../ARCHITECTURE.md`
- `../docs/dev/backend.md`
- `../docs/architecture/persistence-and-read-models.md`
- `../docs/operations/deployment.md`
