# Runtime 基础设施边界

本文记录 SQL/read-model 收敛第一阶段的基础设施边界。当前只建立队列、worker、Redis、对象存储和观测入口，不切换具体业务模块读写路径。

## PostgreSQL Durable Queue

权威队列表是 `job.outbox_events`。Repository 位于：

- `backend/src/fin_ops_platform/services/runtime_queue.py`

支持能力：

- `enqueue(...)`：写入 pending event，支持 `tenant_id`、`scope_type`、`scope_key`、`dedupe_key`、`source_version`、`priority`、`trace_id` 和 JSON payload。
- `enqueue_read_model_refresh(...)`：同步 upsert `job.read_model_dirty_scopes` 并写 read model refresh outbox event。
- `claim_next(...)`：按 `event_type` 过滤，使用 PostgreSQL row lock 与 `for update skip locked` claim。
- `ack_event(...)` / `complete(...)`：只有持有 `processing + locked_by` 的 worker 可以完成，并把 handler `duration_ms` 写入 `raw_payload.runtime_result`。
- `fail(..., retry=True)` / `retry(...)`：释放锁并按 `available_at` 延后重试。
- `fail(..., retry=False)`：标记 failed，保留 `last_error` 和 `processed_at`。
- `fail_event(...)`：生产 worker 失败入口；可重试错误按指数退避回到 pending，超过 `max_attempts` 进入 `dead_lettered`。
- `requeue_event(...)`：运维修复后把 `failed|dead_lettered|pending` 事件重新置为 pending，并保留 `raw_payload.manual_requeue`。

Schema 约束：

- `job.outbox_events.status` 只允许 `pending|processing|done|failed|dead_lettered`。
- `(tenant_id, dedupe_key)` 只对 pending event 使用 partial unique index；processing 期间同 scope 新版本必须能产生新的 pending event，避免刷新中新增版本丢失。
- `attempt_count` 与 `attempts` 通过 trigger 保持兼容同步。
- `source_version`、`priority`、`trace_id`、`schema_version` 是 outbox 物理字段；`job.runtime_outbox_envelope_v1` 暴露未来 RabbitMQ publisher 可读取的 envelope 视图。

RabbitMQ envelope 只能包含 routing identity 和版本：

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "event_type": "workbench.read_model.refresh",
  "scope_type": "workbench",
  "scope_key": "all",
  "source_version": 123,
  "priority": "normal",
  "trace_id": "trace-id"
}
```

## Queue Backend 配置边界

当前默认仍是 PostgreSQL durable queue；生产需要低延迟唤醒和横向扩展 worker 时，可以启用 RabbitMQ 传输层。RabbitMQ 只投递 outbox envelope，不能替代 PostgreSQL 事实源。

```text
FIN_OPS_QUEUE_BACKEND=postgres
RABBITMQ_URL=amqp://rabbitmq.internal
RABBITMQ_VHOST=/finops
RABBITMQ_EXCHANGE=finops.events
RABBITMQ_WORKBENCH_QUEUE=finops.workbench.read_model.refresh
RABBITMQ_WORKBENCH_ROUTING_KEY=workbench.read_model.refresh
RABBITMQ_DEAD_LETTER_EXCHANGE=finops.events.dlx
RABBITMQ_WORKBENCH_DEAD_LETTER_QUEUE=finops.workbench.read_model.refresh.dlq
RABBITMQ_PREFETCH=10
RABBITMQ_PUBLISH_CONFIRM=true
RABBITMQ_HEARTBEAT_SECONDS=60
RABBITMQ_BLOCKED_CONNECTION_TIMEOUT_SECONDS=300
RABBITMQ_MANAGEMENT_URL=http://rabbitmq.internal:15672
RABBITMQ_MANAGEMENT_USERNAME=finops_monitor
RABBITMQ_MANAGEMENT_PASSWORD=***
RABBITMQ_MANAGEMENT_TIMEOUT_SECONDS=2
RABBITMQ_SHADOW_PUBLISH=false
```

`FIN_OPS_QUEUE_BACKEND` 默认 `postgres`，只允许 `postgres|rabbitmq`。设置为 `rabbitmq` 后，worker 改为 RabbitMQ consumer 模式，但收到消息后仍必须回 PostgreSQL 用 `event_id` claim `job.outbox_events`。RabbitMQ 消息体不得携带 read model payload、页面 snapshot 或任何业务事实。

RabbitMQ 拓扑通过显式 CLI 创建，应用启动不会偷偷声明生产资源：

```bash
FIN_OPS_QUEUE_BACKEND=rabbitmq \
RABBITMQ_URL=amqps://finops_dispatcher:***@rabbitmq.internal:5671/%2Ffinops \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.rabbitmq_topology --check

FIN_OPS_QUEUE_BACKEND=rabbitmq \
RABBITMQ_URL=amqps://finops_dispatcher:***@rabbitmq.internal:5671/%2Ffinops \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.rabbitmq_topology --apply
```

标准拓扑覆盖所有已迁入 RabbitMQ 的 runtime event。队列名称默认由 `RABBITMQ_QUEUE_PREFIX` 加 event type 生成，例如：

- exchange：`finops.events`，`topic`，durable。
- queue：`finops.workbench.read_model.refresh`、`finops.search.read_model.refresh`、`finops.pending_invoice.read_model.refresh`、`finops.cost_statistics.read_model.refresh`、`finops.tax_offset.read_model.refresh`、`finops.oa.sync`、`finops.file_object.gridfs_migration`、`finops.import.process.requested`，durable。
- routing key：对应 event type。
- DLX：`finops.events.dlx`。
- DLQ：每个 queue 对应 `<queue>.dlq`。

RabbitMQ publisher 是独立进程，从 PostgreSQL claim publishable event，只有 publisher confirm 成功后才把 outbox 标记为 `publish_status='published'`：

```bash
FIN_OPS_QUEUE_BACKEND=rabbitmq \
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://fin_ops_worker:***@postgres.internal:5432/fin_ops \
RABBITMQ_URL=amqps://finops_dispatcher:***@rabbitmq.internal:5671/%2Ffinops \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.rabbitmq_dispatcher \
  --publisher-id rabbitmq-dispatcher-1 \
  --batch-size 100 \
  --lock-timeout-seconds 300 \
  --retry-delay-seconds 60
```

导入确认的执行路径由 `FIN_OPS_IMPORT_PROCESSING_BACKEND` 控制：

- `inline`：请求线程按旧路径执行，作为回滚边界。
- `rabbitmq`：API 只创建 `job.import_jobs` 和 `import.process.requested` outbox event；worker 回 PostgreSQL 读取 import job 后执行 processor。
- 未显式设置时，`FIN_OPS_QUEUE_BACKEND=rabbitmq` 会默认启用 `rabbitmq` 导入处理；否则默认 `inline`。

灰度阶段可以保持 `FIN_OPS_QUEUE_BACKEND=postgres`，只启动 shadow publish：

```bash
FIN_OPS_QUEUE_BACKEND=postgres \
RABBITMQ_SHADOW_PUBLISH=true \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.rabbitmq_dispatcher --shadow-publish --check
```

consumer 模式使用同一个 worker 入口。切到 `FIN_OPS_QUEUE_BACKEND=rabbitmq` 后，worker 不再 polling claim，而是从 RabbitMQ 收到 envelope，再回 PostgreSQL claim event：

```bash
FIN_OPS_QUEUE_BACKEND=rabbitmq \
FIN_OPS_POSTGRES_DATABASE_URL=postgresql://fin_ops_worker:***@postgres.internal:5432/fin_ops \
RABBITMQ_URL=amqps://finops_worker:***@rabbitmq.internal:5671/%2Ffinops \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker \
  --enable-workbench-read-model-refresh \
  --worker-kind workbench-read-model \
  --event-type workbench.read_model.refresh \
  --lock-timeout-seconds 300 \
  --task-timeout-seconds 60 \
  --statement-timeout-seconds 30 \
  --max-attempts 5
```

回滚只需要停止 dispatcher/consumer 并恢复 `FIN_OPS_QUEUE_BACKEND=postgres`；PostgreSQL outbox、dirty scopes、attempts、failed/dead_lettered 和 publish 状态不会丢失。

## 独立 Worker

独立入口：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check
```

持续运行：

```bash
FIN_OPS_POSTGRES_DATABASE_URL='postgres://fin_ops_worker:***@postgres.internal:5432/fin_ops' \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.app.worker
```

重要参数：

```bash
python3 -m fin_ops_platform.app.worker \
  --worker-id runtime-worker-1 \
  --worker-kind workbench-read-model \
  --poll-interval-seconds 5 \
  --lock-timeout-seconds 300 \
  --retry-delay-seconds 60 \
  --max-attempts 5
```

业务 handler 通过 worker CLI 显式启用。生产建议按 handler 家族拆进程，并用 `--event-type` 限定 claim 范围，避免通用 worker 抢占未知业务事件。

Worker 正确性边界：

- PostgreSQL 是唯一 durable queue。
- Redis 不可用时，worker 仍通过 PostgreSQL polling claim job。
- Worker crash 后，`processing` 且 `locked_at` 超过 timeout 的 event 可被其他 worker 抢占。
- handler 抛出异常时任务回到 `pending` 并按 `available_at` 延后。
- 同一 event 可能被重复投递或重复 claim；handler 必须用 `event_id/source_version/scope` 做幂等保护。
- 旧 `source_version` 不能覆盖新 read model，也不能把更高版本 dirty scope 标记为 done。
- 超过最大次数的事件进入 PostgreSQL `dead_lettered`，不是只依赖 RabbitMQ DLQ。

## Redis 边界

Helper 位于：

- `backend/src/fin_ops_platform/services/runtime_redis.py`

配置：

```text
FIN_OPS_REDIS_URL=redis://redis.internal:6379/0
FIN_OPS_REDIS_KEY_PREFIX=finops
FIN_OPS_REDIS_WAKEUP_CHANNEL=finops:runtime:wakeup
FIN_OPS_REDIS_DEFAULT_TTL_SECONDS=60
```

允许用途：

- 短 TTL JSON cache。
- `PUBLISH` wakeup，减少 worker polling 延迟。
- `SET NX EX` 辅助锁。

禁止用途：

- 业务事实源。
- read model 唯一存储。
- durable queue。
- 文件迁移进度的唯一记录。

无 Redis 配置时，`RuntimeRedisHelper.disabled()` 为 no-op；这不是错误状态。

## Object Storage 骨架

接口与配置位于：

- `backend/src/fin_ops_platform/services/object_storage.py`

配置：

```text
OBJECT_STORAGE_BACKEND=minio
S3_ENDPOINT_URL=http://minio.internal:9000
S3_BUCKET=fin-ops-files
S3_REGION=cn-north-1
S3_ACCESS_KEY_ID=***
S3_SECRET_ACCESS_KEY=***
```

`OBJECT_STORAGE_BACKEND` 支持：

- `local`：默认禁用对象存储，只保留配置边界。
- `minio`：S3-compatible MinIO。
- `s3`：S3-compatible 对象存储。

PostgreSQL mode 启用 `OBJECT_STORAGE_BACKEND=minio|s3` 后，新上传文件通过 `ObjectStorageRepository` 写入临时对象、校验 sha256/size、写最终对象，并只暴露 `app.file_objects.migration_status='verified'` 的对象给业务读取。未配置对象存储时仍保留本地开发兼容路径。

GridFS backfill、校验、清理和短期回滚见 `docs/operations/object-storage-minio.md`。

## 观测

PostgreSQL mode 的 `/health` readiness summary 会通过 `PostgresStateStore.health_summary()` 附带 `runtime_infrastructure`，内容包括：

- `queue_backlog`：按 outbox status 聚合。
- `dirty_scopes`：按 dirty scope status 聚合。
- `failed_jobs`：failed/dead-lettered outbox 数量。
- `max_pending_age_seconds`：pending job 最大等待时间。
- `oldest_pending_event_age_seconds`：最老 pending event age，兼容 `max_pending_age_seconds`。
- `worker_heartbeat_lag_seconds`：最近 worker heartbeat lag。
- `read_model_refresh_duration_ms`：worker ack 写回的 read model refresh p50/p95/p99。
- `read_model_refresh_failure_rate`：read model refresh 失败和 dead-letter 比例。
- `stale_dirty_scope_count`：超时 dirty scope 数量。
- `stale_dirty_scopes`：最多 20 条 stale dirty scope 摘要。
- `workbench_read_model_status_metric`：`/api/workbench/summary|groups` 遇到 `refreshing|stale|unavailable` 时输出结构化计数日志。
- `redis_hit_count` / `redis_miss_count`：进程内 Redis helper 命中/未命中计数。

这些指标来自 PostgreSQL 表，Redis 清空或不可用不会影响指标正确性。

`/api/workbench/refresh-status` 继续返回 workbench-only 的 dirty scopes、worker lag、last error 和 outbox backlog。`/api/workbench/summary` 与 `/api/workbench/groups` 会输出结构化 `workbench_api_metric` 日志，生产日志/指标系统按 `endpoint=/api/workbench/summary|/api/workbench/groups` 聚合 p95。

## 最终收口验证 Harness

RabbitMQ staging preflight：

```bash
FIN_OPS_TEST_DATABASE_URL=postgresql://fin_ops_test:***@postgres.internal:5432/fin_ops_test \
RABBITMQ_TEST_URL=amqps://finops_test:***@rabbitmq.internal:5671/%2Ffinops \
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight --json
```

该命令会跑真实 PostgreSQL runtime queue integration、真实 RabbitMQ 临时 topology/publish/consume、topology check、dispatcher shadow check 和 RabbitMQ consumer worker check。没有 `FIN_OPS_TEST_DATABASE_URL` 或 `RABBITMQ_TEST_URL` 时会失败并列出缺项。

收口执行入口：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_runtime_convergence_closure \
  --json \
  --run-unit-tests \
  --output docs/database-migration/reports/runtime-convergence-closure-latest.json
```

该命令会执行静态边界检查、剩余 `_load_snapshot(...)` 分类检查、worker 配置检查、PostgreSQL/Redis/MinIO/OA 探测和目标测试。没有配置真实基础设施时，真实环境项会标为 `skip`，整体状态不会是 `pass`。

生产 cutover 前必须在真实环境中设置：

```text
FIN_OPS_TEST_DATABASE_URL=postgresql://...
FIN_OPS_REDIS_URL=redis://...
OBJECT_STORAGE_BACKEND=minio
S3_ENDPOINT_URL=http://...
S3_BUCKET=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
FIN_OPS_OA_MONGO_HOST=...
FIN_OPS_OA_MONGO_DATABASE=...
FIN_OPS_OA_MONGO_PORT=27017
FIN_OPS_OA_MONGO_USERNAME=...
FIN_OPS_OA_MONGO_PASSWORD=...
FIN_OPS_APP_MONGO_HOST=...
FIN_OPS_APP_MONGO_DATABASE=...
FIN_OPS_APP_MONGO_PORT=27017
FIN_OPS_APP_MONGO_USERNAME=...
FIN_OPS_APP_MONGO_PASSWORD=...
```

然后运行强制模式：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_runtime_convergence_closure \
  --json \
  --require-real-infra \
  --run-unit-tests \
  --output docs/database-migration/reports/runtime-convergence-closure-require-real-infra.json
```

强制模式只有在真实 PostgreSQL、Redis、MinIO/S3、App Mongo/GridFS 迁移源、OA Mongo source 只读探测、worker check 和 read model 性能探测全部通过时才返回 `pass`。`FIN_OPS_APP_MONGO_*` 只用于 `file_object.gridfs_migration` worker smoke，会执行一次 GridFS backfill、checksum verify 和 orphan cleanup；生产 API 主路径仍不能配置 GridFS fallback。任何缺失配置或不可达基础设施都会返回 `fail`，不能作为生产收口完成。
