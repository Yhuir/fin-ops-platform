# Backend

后端是 Python 服务，负责导入解析、OA 接入、关联工作台、核销、台账、税金、ETC、成本统计、设置、后台任务和 app health。

## 目录

```text
backend/src/fin_ops_platform/
  app/       HTTP 入口、路由、OA 鉴权、响应组装
  domain/    领域模型和枚举
  services/  业务服务、适配层、持久化、读模型和后台任务
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

本地和服务器同构运行时必须先通过：

```bash
./scripts/check-local-runtime.sh --dependencies-only
```

`./scripts/start-backend.sh` 会在 PostgreSQL runtime 下自动执行该检查。后端启动后可用：

```bash
./scripts/check-local-runtime.sh --require-backend
```

确认 `/health`、PostgreSQL、Redis、MinIO/S3 和 `/api/workbench?month=all` 都正常。

## 测试

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

## 持久化

- 生产主读写通过 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 和 `FIN_OPS_APP_READ_BACKEND=postgres` 接入 PostgreSQL。
- PostgreSQL 连接使用 `FIN_OPS_POSTGRES_DATABASE_URL` 或 `DATABASE_URL`，生产环境应从 root-only credential file 注入。
- app Mongo 旧路径仍保留，用于迁移观察期回滚、shadow-read、导出和审计工具。
- OA 数据库保持只读，只能通过 `MongoOAAdapter` 读取，不能作为 app 写库。

## Worker

生产 read model 刷新使用独立 worker 进程，不依赖 API 进程内 thread。worker 通过 PostgreSQL durable queue claim 任务，Redis 只做短 TTL cache 和 wake-up：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check
```

常用角色：

- `worker-oa-sync`：`--enable-oa-sync --event-type oa.sync`
- `worker-workbench`：`--enable-workbench-read-model-refresh --event-type workbench.read_model.refresh`
- `worker-search`：`--enable-search-read-model-refresh --event-type search.read_model.refresh`
- `worker-pending-invoice`：`--enable-pending-invoice-read-model-refresh --event-type pending_invoice.read_model.refresh`
- `worker-cost-tax`：`--enable-cost-statistics-read-model-refresh --enable-tax-offset-read-model-refresh --event-type cost_statistics.read_model.refresh --event-type tax_offset.read_model.refresh`
- `worker-file-migration`：`--enable-file-object-migration --event-type file_object.gridfs_migration`

生产或本地补数 worker 必须带明确的卡死释放和 SQL statement timeout，例如：

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

全量补数入口：

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

read model refresh worker 不构造完整 `Application`，不调用 `StateStore.load()`；`all` scope 会展开成 month/entity shard 后再处理。

## 相关文档

- `../ARCHITECTURE.md`
- `../docs/dev/backend.md`
- `../docs/architecture/persistence-and-read-models.md`
- `../docs/operations/deployment.md`
