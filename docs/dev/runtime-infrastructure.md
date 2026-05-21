# Runtime 基础设施边界

本文记录 SQL/read-model 收敛第一阶段的基础设施边界。当前只建立队列、worker、Redis、对象存储和观测入口，不切换具体业务模块读写路径。

## PostgreSQL Durable Queue

权威队列表是 `job.outbox_events`。Repository 位于：

- `backend/src/fin_ops_platform/services/runtime_queue.py`

支持能力：

- `enqueue(...)`：写入 pending event，支持 `tenant_id`、`scope_type`、`scope_key`、`dedupe_key` 和 JSON payload。
- `claim_next(...)`：按 `event_type` 过滤，使用 PostgreSQL row lock 与 `for update skip locked` claim。
- `complete(...)`：只有持有 `processing + locked_by` 的 worker 可以完成。
- `fail(..., retry=True)` / `retry(...)`：释放锁并按 `available_at` 延后重试。
- `fail(..., retry=False)`：标记 failed，保留 `last_error` 和 `processed_at`。

Schema 约束：

- `job.outbox_events.status` 只允许 `pending|processing|done|failed`。
- `(tenant_id, dedupe_key)` 对 active event 使用 partial unique index 防重复。
- `attempt_count` 与 `attempts` 通过 trigger 保持兼容同步。

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
  --poll-interval-seconds 5 \
  --lock-timeout-seconds 300 \
  --retry-delay-seconds 60
```

当前阶段没有注册业务 handler，默认不会 claim 任何 event。后续模块接入时应显式注册 handler 或限定 `event_types`，避免通用 worker 抢占未知业务事件。

Worker 正确性边界：

- PostgreSQL 是唯一 durable queue。
- Redis 不可用时，worker 仍通过 PostgreSQL polling claim job。
- Worker crash 后，`processing` 且 `locked_at` 超过 timeout 的 event 可被其他 worker 抢占。
- handler 抛出异常时任务回到 `pending` 并按 `available_at` 延后。

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
- `failed_jobs`：failed outbox 数量。
- `max_pending_age_seconds`：pending job 最大等待时间。
- `stale_dirty_scope_count`：超时 dirty scope 数量。
- `stale_dirty_scopes`：最多 20 条 stale dirty scope 摘要。

这些指标来自 PostgreSQL 表，Redis 清空或不可用不会影响指标正确性。

## 最终收口验证 Harness

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
