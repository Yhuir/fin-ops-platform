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
- 关联台继续读取 `read_model.workbench_*` active generations，并保留 reader、writer、worker 与 retention timer；其它目标页面直接读取 canonical facts，不得借用该 projection。
- Runtime queue 历史有受控保留策略：`job.outbox_events` 与
  `job.read_model_dirty_scopes` 只删除 `status='done'` 的完成态历史，默认保留 30 天且每个
  event/scope type 至少保留最近 512 条，dirty scope 还会按
  `(tenant_id, scope_type, scope_key)` 保留最新 done 行以保持后续 source_version 递增，单批最多
  20000 行。pending、processing、failed、dead-lettered 以及仍可作为失败诊断证明的
  same-scope done outbox 不被 retention 删除。
  生产通过版本化部署的 `finops-prune-runtime-queue-history.timer` 执行，helper 读取 root-only
  `fin-ops.postgres-migrator.env`，只把 delete 权限授予 migrator 角色，不扩大 API/worker
  数据库权限。

Runtime queue 历史排障边界：

```sql
select status, count(*)
from job.outbox_events
group by status
order by status;

select status, count(*)
from job.read_model_dirty_scopes
group by status
order by status;

select
  n.nspname,
  c.relname,
  pg_size_pretty(pg_total_relation_size(c.oid)) as total_size
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'job'
  and c.relname in ('outbox_events', 'read_model_dirty_scopes')
order by pg_total_relation_size(c.oid) desc;
```

手工执行时先 dry-run：

```bash
PYTHONPATH=/opt/fin-ops/releases/<release>/src/backend/src \
  FIN_OPS_POSTGRES_DATABASE_URL="$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops prune-history \
  --dry-run --keep-days 30 --keep-recent-per-type 512 --limit 20000
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

## App Mongo 退役边界

App Mongo 旧数据可以在迁移观察期继续保留，用于回滚参考、shadow-read 差异分析或审计取证；它不是 PostgreSQL primary runtime 的 app 事实源，也不应参与日常 clean-state 验证。

移除或停用 App Mongo 前必须完成：

- 确认生产 API、worker、read model refresh、维护脚本和导出工具均使用 PostgreSQL primary。
- 导出并归档 app Mongo 旧集合或 snapshot，记录归档位置、时间和负责人。
- 确认 `.runtime/fin_ops_platform/app_mongo_config.json` 不再被生产 runtime 读取，观察 `runtime-check`、`/health`、worker、关键页面和导出。
- 禁止用 app Mongo 旧 snapshot 回写 PostgreSQL；差异只能通过审计 repair、补偿脚本或 outbox 重投递修复。
- 不得删除 OA Mongo 配置或数据。OA Mongo 是外部只读来源，和 app Mongo 退役不是同一件事。

## 备份和恢复

最低要求：

- 定期 `pg_dump` 逻辑备份，用于表级恢复和迁移验证。
- 生产建议接入 WAL 归档和 PITR。
- staging 定期恢复演练，验证 schema、关键表数量、read model rebuild 和 worker drain。
- 备份状态纳入监控。

更多备份规则见 `backup-and-recovery.md`。

## 验证命令

干净 app check 和全量本地回归：

```bash
bash scripts/verify.sh backend
```

当前配置 runtime app check：

```bash
bash scripts/verify.sh runtime-check
```

旧运行时 SQL/read-model 收敛报告工具已删除。当前收口验证使用分项 gate：`scripts/verify.sh runtime-check`、RabbitMQ staging preflight、deploy examples tests、worker `--check` 和对应模块测试。

RabbitMQ staging preflight 如启用 RabbitMQ：

```bash
set -a
source /etc/fin-ops/fin-ops.api.env
source /etc/fin-ops/fin-ops.rabbitmq-monitoring.env
set +a
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
  --json \
  --output /tmp/finops-rabbitmq-staging-preflight.json
```

默认只检查 registry 中 `required=true` 且 `rabbitmq_eligible=true` 的 worker。`--include-optional-workers`
只用于未来显式登记的 optional worker；当前没有 legacy GridFS file-migration worker。

生产 RabbitMQ worker env 拆分：

- `/etc/fin-ops/fin-ops.rabbitmq-topology.env` 只给 topology bootstrap 使用。
- `/etc/fin-ops/fin-ops.rabbitmq-monitoring.env` 只给 API/运维读取 Management metrics 使用。
- `/etc/fin-ops/fin-ops.rabbitmq-worker.env` 只保存 worker consumer 共享 `RABBITMQ_URL`，权限 `0600 root root`，不得设置 `FIN_OPS_QUEUE_BACKEND`。
- `/etc/fin-ops/fin-ops.worker.<instance>.env` 控制单个 worker 是否从 `postgres` 切到 `rabbitmq`。

2026-06-13 生产 Stage 9 已把 required RabbitMQ eligible worker 切到 real consumers。验收时
`/health/ready` 中 `rabbitmq_consumer_count=15`、`rabbitmq_queue_depth=0`、`rabbitmq_dlq_count=0`、
`rabbitmq_metric_error=null`，PostgreSQL dirty/outbox/readiness 同时保持收敛。回滚时只需要恢复
per-worker env 到 `FIN_OPS_QUEUE_BACKEND=postgres` 并重启 worker；不要把 RabbitMQ 队列作为
read model 状态事实源。

一次性报告不要写入长期文档树。需要长期保留的结论应提炼到本文或对应运维文档。
