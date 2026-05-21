# 73. Runtime Read Model And Object Storage Phase 2 Cutover

```text
/goal 执行 runtime SQL/read-model 收敛阶段 2：发布业务 read model worker/backfill、配置 MinIO/S3、迁移 GridFS 文件并校验，最后在确认 verified 后移除 FIN_OPS_ENABLE_LEGACY_GRIDFS_READS。

上下文：
- 仓库：/Users/yu/Desktop/fin-ops-platform
- 服务器：139.155.5.132
- 阶段 1 已完成：
  - 生产 API 已切到 `/opt/fin-ops/releases/runtime-sql-read-model-20260521161944`
  - `/health` 显示 `storage.backend=postgres`、schema version 9
  - `job.read_model_dirty_scopes`、`job.runtime_worker_heartbeats` 已存在
  - `FIN_OPS_STORAGE_MODE=postgres`
  - `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1` 临时开启，保护 523 个 GridFS 历史文件
  - 备份位于 `/opt/fin-ops/backups/runtime_release_preflight_20260521161243/`
- 当前仍未完成：
  - `read_model.workbench_rows = 0`
  - `app.file_objects` 仍有 523 条 `storage_backend='gridfs'`
  - 未配置 MinIO/S3
  - 未执行业务 read model backfill

硬边界：
1. 不允许在 MinIO/S3 backfill + checksum verify 完成前移除 `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1`。
2. 不允许在 worker/backfill smoke 失败时声明 runtime SQL read model 收敛完成。
3. 不允许删除 GridFS 数据或对象存储对象；删除只做 tombstone/cleanup worker，且必须可重试。
4. 不允许让 API 回到 Mongo 或 `FIN_OPS_STORAGE_MODE=mongo_only`。
5. 任何生产切换失败，立即把 systemd drop-in 指回阶段 1 release，不做数据库回滚。

串行任务：
1. 本地阶段 2代码审计
   - 读取 `git status --short`、`git diff --stat`、`git log --oneline --max-count=5`。
   - 明确阶段 2包含：
     - `app/worker.py` 业务 handler 开关。
     - `object_storage.py`、`file_object_migration.py`、verify/rollback 工具。
     - workbench/cost/tax/search/pending/OA read model refresh services。
     - read model repository 和 API SQL path。
     - `0009_runtime_infrastructure.sql` 的对象存储字段、pending_invoice_rows、OA scope 字段等补齐。
   - 确认不包含无关 UI/业务口径改动。

2. 本地验证
   - 运行：
     - `python -m compileall -q backend/src/fin_ops_platform`
     - `git diff --check`
     - `python -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_bootstrap.py tests/test_runtime_monitoring.py tests/test_runtime_redis.py tests/test_object_storage_repository.py tests/test_file_object_storage.py tests/test_postgres_migrations.py -q`
     - `python -m pytest tests/test_workbench_sql_runtime.py tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_search_pending_sql_runtime.py tests/test_oa_projection_sql_runtime.py -q`
   - 任何失败必须修复后再继续。

3. 服务器阶段 2前备份
   - 再次生成 PostgreSQL dump 和 systemd/env 备份：
     - `/opt/fin-ops/backups/runtime_phase2_preflight_YYYYMMDDHHMMSS/`
   - 确认 `/health` 仍是 PostgreSQL。

4. 配置本机 MinIO/S3
   - 如果服务器没有 MinIO：
     - 安装 MinIO 到 `/opt/minio/minio`。
     - 建立数据目录 `/opt/minio/data`。
     - 创建 systemd service，绑定 `127.0.0.1:9000`，console 绑定 `127.0.0.1:9001`。
     - 生成强随机 root user/password，写入 `/etc/minio/minio.env`，权限 600。
   - 创建 bucket：`fin-ops-files`。
   - 若无 `mc`，用 Python/boto3 初始化 bucket。
   - 不对公网暴露 MinIO 端口。

5. 创建阶段 2 release
   - 新建 `/opt/fin-ops/releases/runtime-sql-read-model-phase2-YYYYMMDDHHMMSS/`。
   - 上传 backend 源码，不覆盖阶段 1 release。
   - 创建独立 venv，安装 `backend/requirements.txt`。
   - 确认 `psycopg`、`redis`、`boto3`、`pymongo`、`gridfs` 可 import。

6. 阶段 2 schema smoke
   - 使用阶段 2 release 代码补齐 0009 后续字段。
   - 因服务器历史 migration 0004-0007 存在 checksum mismatch，不跑全量 `migrate apply`。
   - 只对 0009 做幂等 apply 或手动执行补齐 SQL，必须先备份。
   - 确认：
     - `app.file_objects` 有 `temporary_object_key`、`source_storage_backend`、`source_storage_uri`、`last_error`、`uploaded_at`、`verified_at`、`failed_at`、`tombstoned_at`。
     - `read_model.pending_invoice_rows` 存在。
     - `read_model.search_index_rows.cache_status` 存在。
     - `read_model.tax_offset_read_models.schema_version/cache_status` 存在。
     - `app.oa_applications.scope_month` 存在。

7. GridFS 到 MinIO/S3 backfill smoke
   - 配置阶段 2 worker env：
     - `OBJECT_STORAGE_BACKEND=minio`
     - `S3_ENDPOINT_URL=http://127.0.0.1:9000`
     - `S3_BUCKET=fin-ops-files`
     - `S3_REGION=us-east-1`
     - `S3_ACCESS_KEY_ID`
     - `S3_SECRET_ACCESS_KEY`
   - 先用 `--max-iterations` 或小 limit 迁移 1-5 个文件。
   - 校验 sha256、size、etag，并确认业务读取同一文件可读。
   - 再执行全量 backfill。
   - 运行 verify 工具确认 523 个文件全部 `verified`。
   - 若任何 checksum mismatch 或 read failure，停止并保留 `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1`。

8. 业务 read model backfill smoke
   - 先投递单月 scope：
     - workbench
     - cost_statistics
     - tax_offset
     - search
     - pending_invoice
   - 用阶段 2 worker `--max-iterations` 处理。
   - 验证 SQL read model 表有数据，API smoke 不 500。
   - 再按月份全量 backfill。
   - 记录 `job.outbox_events`、`job.read_model_dirty_scopes` pending/failed/backlog。

9. 切换 API 到阶段 2 release
   - 更新 systemd drop-in 到阶段 2 release。
   - 保留 PostgreSQL env。
   - 配置 MinIO/S3 env。
   - 仅当所有 file_objects 均 verified 后，移除 `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1`。
   - 重启 API。
   - `/health` 必须仍为 PostgreSQL。
   - 主要 API smoke 不 500。

10. 收尾验证
   - `app.file_objects` 无未验证 GridFS 生产读取依赖。
   - `read_model.workbench_rows > 0`。
   - worker heartbeat 存在。
   - queue 无 failed，或 failed 有明确错误且不影响 cutover。
   - MinIO service active，bucket 可读写。
   - 记录最终 release、备份路径、回滚路径。

可并行任务：
- A: 本地测试和阶段 2 release 打包。
- B: 服务器 MinIO 安装和 bucket 初始化。
- C: 0009 schema 补齐和数据库验证。
- D: GridFS migration/verify smoke。
- E: read model worker/backfill/reconciliation smoke。

完成门槛：
- API 仍接 PostgreSQL，不回到 Mongo。
- MinIO/S3 已配置并通过 put/get/delete smoke。
- 523 个 GridFS 历史文件迁移到对象存储并 verified。
- `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1` 仅在全部 verified 后移除。
- 工作台、成本、税金、搜索、待找发票 read model worker 至少完成 smoke，且 `read_model.workbench_rows > 0`。
- queue/dirty scope/worker heartbeat 可观测。
- 有明确备份和回滚路径。
```
