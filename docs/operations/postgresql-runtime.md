# PostgreSQL Runtime

本文保留 PostgreSQL 迁移完成后的当前运行事实和生产运维边界。历史阶段细节见 `../references/postgresql-migration-history.md`。

## 当前状态

截至迁移完成记录，production `fin-ops.service` 已切到 PostgreSQL primary runtime：

```text
FIN_OPS_APP_STORAGE_BACKEND=postgres
FIN_OPS_APP_READ_BACKEND=postgres
FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary
```

运行口径：

- app 业务事实、设置、任务状态、read model 主读写使用 PostgreSQL。
- OA MongoDB 继续作为外部只读源，不写入、不建索引、不修复源集合。
- app Mongo 旧路径只作为迁移观察期回滚、shadow-read 和审计参考，不作为当前开发入口。
- PostgreSQL schema 使用 `app`、`read_model`、`job`、`audit` 等 schema。
- Read model refresh 事实源为 `job.outbox_events` 与 `job.read_model_dirty_scopes`。

## 账号和权限

生产账号需要分离：

| 账号 | 用途 |
| --- | --- |
| migrator | schema migration 和 DDL。 |
| API/runtime | HTTP API 主读写。 |
| worker | worker、read model refresh、job queue。 |
| readonly | 备份、审计、只读排障。 |

密码和 `DATABASE_URL` 只能放在服务器 root-only env file 或密钥系统，不写入 git。

## Queue 和 Read Model

- 所有 refresh 请求必须通过 `RuntimeQueueRepository.enqueue_read_model_refresh(...)` 或事务内 writer。
- 业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。
- Worker 从 durable queue claim event，重建 SQL projection 后 complete dirty scope。
- Redis 只缓存 freshness gate 后的 payload。
- RabbitMQ 只能作为可选 transport/wakeup，不能替代 PostgreSQL dirty scope 状态。
- Workbench read model generation 有保留策略：发布新 active generation 后自动 bounded prune 旧的
  非 active generation；生产同时使用 `finops-prune-workbench-generations.timer` 兜底，避免
  `read_model.workbench_*` 历史 generation 长期堆积。

Workbench read model 表空间排障边界：

```sql
select status, count(*)
from read_model.workbench_generations
group by status
order by status;

select
  relname,
  pg_size_pretty(pg_total_relation_size(c.oid)) as total_size
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'read_model'
  and c.relname like 'workbench_%'
order by pg_total_relation_size(c.oid) desc;
```

普通 `delete`/`vacuum` 只能让 PostgreSQL 复用空间，不保证把空间还给文件系统。只有
`TRUNCATE`、`VACUUM FULL`、`pg_repack` 或表重建会降低 `df` 看到的占用；其中 `VACUUM FULL` 和
`pg_repack` 需要额外重写空间。Workbench read model 属于可重建投影，执行清空/重建必须进入维护
窗口、停止 API/worker、使用精确白名单表名且不使用 `CASCADE`，并通过 rehydrate 验证 fresh。

## 部署和回滚

生产发布入口是：

```bash
./scripts/deploy-oa.sh
```

生产服务应保留：

- 当前 release path。
- Python venv path。
- PostgreSQL runtime env file。
- systemd drop-in 或 service env 摘要。
- 前端静态目录备份。
- `/health` 和关键 `/api/*` smoke 结果。

回滚原则：

- 读回滚可以切回旧 release 或旧 route，但保留 PostgreSQL 现场用于排查。
- PostgreSQL 已成为事实源后，不允许用旧 app Mongo 全量覆盖 PostgreSQL。
- 差异修复必须走补偿脚本、outbox 重投递或明确审计 repair。
- OA Mongo 禁止作为 app 写入目标。

## 备份和恢复

最低要求：

- 定期 `pg_dump` 逻辑备份，用于表级恢复和迁移验证。
- 生产建议接入 WAL 归档和 PITR。
- staging 定期恢复演练，验证 schema、关键表数量、read model rebuild 和 worker drain。
- 备份状态纳入监控。

更多备份规则见 `backup-and-recovery.md`。

## 验证命令

本地 app check：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

运行时 SQL/read-model 收敛报告：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_runtime_convergence_closure \
  --json \
  --require-real-infra \
  --run-unit-tests \
  --output /tmp/finops-runtime-convergence-closure-require-real-infra.json
```

RabbitMQ staging preflight 如启用 RabbitMQ：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
  --json \
  --output /tmp/finops-rabbitmq-staging-preflight.json
```

一次性报告不要写入长期文档树。需要长期保留的结论应提炼到本文或对应运维文档。
