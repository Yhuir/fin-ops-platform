# 72. Production PostgreSQL Runtime Release Hardening

```text
/goal 安全拆分、验证并部署 runtime SQL/read-model 收敛代码到生产服务器，确保服务器继续接入 PostgreSQL，且不会因未完成 MinIO/GridFS 迁移导致历史文件断读。

上下文：
- 仓库：/Users/yu/Desktop/fin-ops-platform
- 当前本地分支：codex/runtime-sql-read-model-convergence
- 服务器：139.155.5.132，当前 fin-ops.service 已通过 systemd drop-in 接入 PostgreSQL。
- 当前服务器事实：
  - /health 显示 storage.mode/backend = postgres。
  - app.file_objects 仍有 523 条 storage_backend='gridfs' 历史文件。
  - read_model.workbench_rows 为 0。
  - job.read_model_dirty_scopes 不存在。
  - 未看到独立 worker service。
  - 未看到 MinIO/S3 生产配置。
- 不允许直接覆盖生产 release，不允许无备份执行 schema 迁移，不允许把 PostgreSQL drop-in 删除后回到 mongo_only。

总目标：
1. 把本地改动拆成可审计的两个阶段，不直接把全量未提交工作区合入 main 后推生产。
2. 第一阶段只发布 schema/queue/worker skeleton/monitoring/显式过渡开关，不切业务文件和 read model 主路径。
3. 第二阶段再发布 read model rebuild、object storage cutover、worker backfill 和业务 API 切换。
4. 部署后服务器 API 仍必须接入 PostgreSQL。
5. GridFS 未迁移到 MinIO/S3 前，历史文件不能断读；过渡兼容必须通过显式环境变量开启，并有移除条件。

串行任务：
1. 本地代码审计和拆分
   - 读取 `git status --short`、`git diff --stat main...HEAD`、`git diff --stat`。
   - 分类本地改动：
     - 阶段 1：`0009_runtime_infrastructure.sql`、`runtime_queue.py`、`runtime_worker.py`、`app/worker.py`、`runtime_monitoring.py`、Redis helper、文档、测试。
     - 阶段 2：workbench/cost/tax/search/OA/file object 业务 cutover、MinIO/GridFS migration、API read path 改造。
   - 不要把阶段 2 业务 cutover 混入阶段 1 部署。

2. GridFS 过渡边界
   - 检查 `PostgresStateStore` 是否默认禁用 legacy GridFS fallback。
   - 增加或确认显式短期变量：`FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1`。
   - 默认情况下不自动构造 legacy GridFS reader。
   - 只有在未配置 ObjectStorage 且显式设置该变量时，才允许 PostgreSQL store 从 data dir 构造 legacy GridFS reader。
   - 增加测试：
     - 默认 production PostgreSQL store 不自动配置 GridFS reader。
     - 显式变量开启时可以配置 reader。
     - 配置 ObjectStorage 后仍不能读 legacy GridFS fallback。

3. 本地验证
   - 运行：
     - `python -m compileall -q backend/src/fin_ops_platform`
     - `python -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_bootstrap.py tests/test_runtime_monitoring.py tests/test_runtime_redis.py tests/test_object_storage_repository.py tests/test_postgres_migrations.py -q`
     - `python -m pytest tests/test_workbench_sql_runtime.py tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_search_pending_sql_runtime.py tests/test_file_object_storage.py -q`
     - `git diff --check`
   - 如任何测试失败，先修复，不进入服务器部署。

4. 服务器发布前只读确认
   - SSH 到服务器，只读确认：
     - `systemctl cat fin-ops.service`
     - `/health` 返回 postgres。
     - 当前 systemd drop-in 包含 `FIN_OPS_APP_STORAGE_BACKEND=postgres`、`FIN_OPS_APP_READ_BACKEND=postgres`、`FIN_OPS_POSTGRES_DATABASE_URL`。
     - 当前 `/opt/fin-ops/fin-ops.env` 是否仍有 `FIN_OPS_STORAGE_MODE=mongo_only`。
     - 统计 `app.file_objects`、`read_model.workbench_rows`、`job.outbox_events`、`job.read_model_dirty_scopes`。
   - 输出结论，不改服务器。

5. 服务器备份
   - 在服务器生成 PostgreSQL 备份：
     - `pg_dump -Fc -d fin_ops -f /opt/fin-ops/backups/fin_ops_pre_runtime_release_YYYYMMDDHHMMSS.dump`
   - 备份 systemd 配置：
     - `/etc/systemd/system/fin-ops.service`
     - `/etc/systemd/system/fin-ops.service.d/*.conf`
     - `/opt/fin-ops/fin-ops.env`
     - `/root/fin_ops_stage23_postgres_runtime.env`
   - 记录备份路径。
   - 没有备份不得执行 migration。

6. Staging/release 目录部署
   - 不覆盖当前 release。
   - 新建 `/opt/fin-ops/releases/runtime-sql-read-model-YYYYMMDDHHMMSS/`。
   - 同步 backend 和必要 web dist。
   - 新建独立 venv 或重建 release venv。
   - 安装 `backend/requirements.txt`，确认 `psycopg`、`redis`、`boto3`、`pymongo`、`gridfs` 可 import。

7. Migration smoke
   - 使用新 release 代码对真实 PostgreSQL 运行 migration smoke。
   - 先 dry-run 或在临时库恢复备份验证；若没有临时库，至少在生产库执行前确认 migration 幂等、DDL 可重复、约束不阻断现有 `storage_backend='gridfs'`。
   - 执行后确认：
     - `job.read_model_dirty_scopes` 存在。
     - `job.runtime_worker_heartbeats` 存在。
     - `read_model.pending_invoice_rows` 存在。
     - `app.file_objects` 有 `migration_status`、`etag`、`updated_at` 等字段。

8. systemd PostgreSQL drop-in hardening
   - 保留并显式设置：
     - `FIN_OPS_APP_STORAGE_BACKEND=postgres`
     - `FIN_OPS_APP_READ_BACKEND=postgres`
     - `FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary`
     - `FIN_OPS_POSTGRES_DATABASE_URL`
     - `PYTHONPATH=<new release>/backend/src`
   - 清理或覆盖旧变量：
     - 不允许 production effective env 继续误导性使用 `FIN_OPS_STORAGE_MODE=mongo_only`。
   - 若 `app.file_objects` 仍有 GridFS 历史记录且 MinIO/S3 未完成，短期开启：
     - `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS=1`
   - 该变量必须写明移除条件：GridFS backfill + checksum verify 完成后删除。

9. API 启动 smoke
   - 切换 systemd 到新 release。
   - 重启 API。
   - 确认：
     - `systemctl status fin-ops.service`
     - `/health` 仍为 postgres。
     - `/health` bootstrap/repositories 信息正常。
     - 主要 API smoke 不返回 500。
   - 若失败，立即回滚 systemd drop-in 到旧 release 和旧 venv，不修改数据库回滚。

10. Worker smoke
   - 先运行：
     - `python3 -m fin_ops_platform.app.worker --check`
   - 再用 `--max-iterations` 对只读或可重复任务做有限 smoke。
   - 确认：
     - `job.runtime_worker_heartbeats` 有记录。
     - `job.outbox_events` claim/complete/retry 语义可用。
     - Redis 不可用时 PostgreSQL polling 仍工作。

11. Read model backfill
   - 先只对一个小 scope/month 做 workbench/cost/tax/search/pending invoice backfill。
   - 对账旧 builder 输出和 SQL read model 输出。
   - 确认 `read_model.workbench_rows` 不再为 0，且页面分页/筛选正确。
   - 全量 backfill 前先确认性能和错误率。

12. MinIO/S3 cutover 准备
   - 如果服务器没有 MinIO/S3，先不要关闭 GridFS 读取。
   - 配置 MinIO/S3 后运行：
     - GridFS backfill worker。
     - checksum verify。
     - orphan cleanup smoke。
   - 全部 `verified` 后删除 `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS`。

可并行任务：
- A: 本地代码拆分、测试和 guard check。
- B: 服务器只读审计、备份脚本和 systemd drop-in 审计。
- C: release 目录/venv/依赖准备。
- D: migration smoke、worker smoke、API smoke 脚本化。
- E: GridFS/MinIO 迁移校验和回滚 playbook。

完成门槛：
- 本地测试和 `git diff --check` 通过。
- 服务器有可恢复 PostgreSQL dump 和 systemd/env 备份。
- 新 release 部署后 `/health` 仍显示 `storage.backend=postgres`。
- `FIN_OPS_STORAGE_MODE=mongo_only` 不再影响 production effective env。
- `job.read_model_dirty_scopes`、`job.outbox_events`、worker heartbeat 可观测。
- GridFS 未迁移前历史文件不因部署断读。
- MinIO/S3 未配置前不宣称文件存储 cutover 完成。
- worker/backfill 未跑通前不宣称 runtime SQL read model 收敛全部完成。
- 回滚路径明确：systemd drop-in 指回旧 release + 旧 venv，PostgreSQL dump 只用于人工灾难恢复，不做静默双写混用。
```
