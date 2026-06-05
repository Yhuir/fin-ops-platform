# 监控与告警

## 当前可观察对象

- `/health` 和 app health API。
- `GET /api/operations/app-health-dashboard` 管理员只读 Dashboard。
- OA 同步状态。
- 工作台 dirty scopes。
- 后台任务状态。
- Runtime durable queue backlog、failed outbox event、stale read model dirty scopes。
- 成本统计缓存预热。
- Mongo 连接错误。
- 导入和重置任务失败。

## 告警建议

生产环境至少关注：

- 后端不可用。
- OA 会话接口不可用。
- App Mongo 写入失败。
- 后台任务连续失败。
- `job.outbox_events` pending 积压时间持续增长。
- `job.outbox_events` failed/dead_lettered 数量非零且持续增加。
- `job.read_model_dirty_scopes` 长时间处于 pending、processing 或 failed。
- `worker_heartbeat_lag_seconds` 持续超过 worker poll interval 与任务超时阈值。
- `missing_required_worker_count > 0` 或 `stale_required_worker_count > 0`。required worker 清单来自 `runtime_worker_registry`；例如 `search-pending-read-model` 缺失会导致搜索/待找发票 read model 长时间 refreshing。
- `read_model_refresh_duration_ms.p95/p99` 持续升高。
- `/api/workbench/summary` 或 `/api/workbench/groups` 的 `workbench_api_metric.duration_ms` p95 超过页面 SLO。
- `/api/workbench/refresh-status` 长时间返回 `refreshing`、`stale`、`failed` 或 `unavailable`。
- `/api/workbench/refresh-status.consistency_status=failed`，或 `read_model.workbench_generation_consistency` 中存在 active inconsistent generation。该状态表示 read model 发布契约被阻断，不能靠浏览器刷新恢复。
- `/health.api_performance.endpoints[*].duration_ms.p95` 持续超过页面 SLO。
- `/health.api_performance.endpoints[*].connection_acquire_ms.p95` 持续升高，表示 PostgreSQL 连接池等待、连接建立或数据库连接资源压力。
- `/health.api_performance.endpoints[*].sql_execute_fetch_ms.p95` 持续升高，表示 SQL 执行/取数本身变慢。
- Redis `redis_miss_count` 快速增长且 PostgreSQL 热读压力同步升高。
- 数据重置任务异常结束。
- 工作台 read model 长时间无法刷新。
- API 返回 `read_model_unavailable`，表示 production PostgreSQL runtime 缺少对应 SQL read repository 或 repository 初始化失败；这不是允许回落旧 snapshot 的场景，应该检查 PostgreSQL 连接、migration 版本和 worker 配置。
- `state:full_state` 在 PostgreSQL `app.app_settings` 中持续更新。生产 API/worker 不应设置 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1`；若出现该 key 写入，应排查是否误用了 migration/shadow/test 配置。

## 日志要求

- 日志应包含请求路径、用户、动作、耗时和错误摘要。
- worker 日志应包含 `queue_event_id`、`event_type`、`attempts`、`trace_id` 和 `source_version`。
- read model API 指标日志使用 `workbench_api_metric`，生产指标系统按 `endpoint` 聚合 p95。
- read model stale/unavailable 计数日志使用 `workbench_read_model_status_metric`，按 `endpoint`、`scope_key`、`read_model_status` 和 `reason` 聚合。
- workbench generation consistency failure 会把 `/api/app-health.workbench_read_model.status` 提升为 `error`，并在 `last_error` 中保留 `generation_metadata_actual_mismatch` 或 all-scope parent inconsistency 原因。
- 工作台实时刷新事件由 `/api/workbench/events` 暴露。SSE 连接失败时前端应回退 `/api/workbench/refresh-status`，运维排障需要同时查看代理是否缓冲 `text/event-stream`、worker lag 和 dirty scope 状态。
- `/health` 输出 `api_performance` 进程内 rolling window 指标，按 `METHOD path` 聚合 `duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_duration_ms` 和 `database_query_count` 的 p50/p95/p99。
- 不输出 token、密码、完整附件正文或敏感原始文件内容。
- 高风险动作需要审计日志，不只依赖应用日志。

## Runtime Queue 指标

`/health` 的 `runtime_infrastructure` 至少包含：

- `queue_backlog`：outbox 按 status 聚合。
- `dirty_scopes`：dirty scope 按 status 聚合。
- `oldest_pending_event_age_seconds`：最老 pending event age。
- `worker_heartbeat_lag_seconds`：runtime worker heartbeat lag。
- `worker_metrics`：按中心 registry 展示 required worker 的 heartbeat。没有 heartbeat 的 required worker 显示 `status=missing` / `warning_code=required_worker_missing`；超过该 worker SLO 的显示 `status=stale` / `warning_code=worker_heartbeat_stale`。
- `missing_required_worker_count` / `stale_required_worker_count`：required worker 缺失或 stale 的数量。
- `read_model_refresh_duration_ms`：read model refresh p50/p95/p99。
- `read_model_refresh_failure_rate`：read model refresh failed/dead-lettered 比例。
- `stale_dirty_scope_count` 和 `stale_dirty_scopes`：超时 dirty scope 摘要。
- `read_model.workbench_generation_consistency`：active workbench generation 的 metadata 与实际 rows/groups 一致性。`inconsistent` 必须按 read model unavailable 处理。
- `redis_hit_count` / `redis_miss_count`：进程内 Redis helper 计数。

RabbitMQ 接入后仍以 PostgreSQL 指标为准；RabbitMQ queue depth 和 DLQ 只能补充投递层健康度，不能代替 outbox/dirty scope 的事实状态。RabbitMQ 相关指标包括：

- `rabbitmq_publish_status`：outbox 按 publish status 聚合。
- `rabbitmq_unpublished_backlog`：等待 dispatcher 投递的 pending outbox 数量。
- `rabbitmq_publish_failed_backlog`：RabbitMQ 发布失败、等待重试的 pending outbox 数量。
- `rabbitmq_dispatcher_lag_seconds`：最老未发布 pending outbox age。
- `rabbitmq_publish_confirm_latency_ms`：publisher confirm p50/p95/p99。
- `rabbitmq_queue_depth`：RabbitMQ workbench queue messages。
- `rabbitmq_unacked_messages`：RabbitMQ unacked delivery 数量。
- `rabbitmq_consumer_count`：RabbitMQ consumer 数量。
- `rabbitmq_dlq_count`：RabbitMQ DLQ 消息数量。
- `rabbitmq_metric_error`：RabbitMQ Management API 不可用或权限错误。

告警建议：

- `rabbitmq_publish_failed_backlog > 0` 且持续 5 分钟。
- `rabbitmq_dispatcher_lag_seconds` 持续超过 worker SLO。
- `rabbitmq_queue_depth` 持续增长且 `consumer_count=0`。
- `rabbitmq_unacked_messages` 长时间不下降。
- `rabbitmq_dlq_count > 0`。
- PostgreSQL `failed/dead_lettered` 增长优先级高于 RabbitMQ DLQ，因为 PostgreSQL 才是失败事实。

## AppHealth 运维状态 Dashboard

设置页 `AppHealth 运维状态` 调用：

```text
GET /api/operations/app-health-dashboard
```

它是管理员只读观测入口，不执行 retry、acknowledge、requeue、republish 或数据修复。生产排障时先看 Dashboard 定位方向，再进入对应 runbook 或后台命令处理。

Dashboard 三个区域：

- `数据`：`app.bank_transactions`、`app.invoices`、`app.oa_applications`、`app.oa_application_items` 的数量和最近同步时间。发票来源拆为普通导入、OA 解析、ETC、手工导入。
- `请求`：当前 API 进程内 rolling window 的 p95/p99，包括完整请求耗时、DB 总耗时、连接获取、SQL execute/fetch 和 SQL 次数。
- `后台`：`job.outbox_events`、RabbitMQ queue/DLQ、`job.runtime_worker_heartbeats`、read model refresh duration 和 dirty scope 计数。

Dashboard API 使用短 TTL 进程内缓存，默认 30 秒，可通过 `FIN_OPS_APP_HEALTH_DASHBOARD_CACHE_TTL_SECONDS` 调整。缓存过期后刷新失败时，接口返回上一份 payload，并在 `freshness.warnings` 中加入 `dashboard_cache_stale_after_error`；权限校验和 PostgreSQL runtime 缺失不走缓存兜底。

判读原则：

- `--` 表示 unknown 或当前无可靠样本，不等于 0。
- RabbitMQ 指标缺失时仍以 PostgreSQL outbox/dirty scopes 为准。
- API/DB p95 同时升高，优先看 PostgreSQL、连接池和 top SQL。
- API p95 升高但 DB 指标不高，优先看 Python 对象构造、JSON 序列化、前端请求量和网络。
- OA 附件发票 inventory 优先读取 `app.oa_attachment_invoice_cache`；`read_model.workbench_rows` 仅作为 fallback，并依赖 `workbench_rows_oa_attachment_inventory_idx` 覆盖索引。
- Read model refresh 的“历史”指标是 bounded history：最近 7 天或每个 event type 最近 512 条完成事件，不是全库永久历史扫描。
- outbox pending 和 RabbitMQ queue 同时增长，优先看 worker/consumer。
- RabbitMQ queue 增长但 outbox 不增长，优先看 broker consumer、prefetch、DLQ 和 ack/nack。

## API/SQL 性能拆分

`/health.api_performance` 是进程内 rolling window，适合本地和单实例快速判断瓶颈：

- `duration_ms`：完整请求耗时。
- `connection_acquire_ms`：从 PostgreSQL pool/direct connection 获取连接的耗时。
- `sql_execute_fetch_ms`：SQL execute 和 fetch 耗时，不含连接获取。
- `database_duration_ms`：连接获取与 SQL execute/fetch 的合计。
- `database_query_count`：当前请求内通过 `PostgresConnection` / `PostgresTransaction` 执行的 SQL 次数。

生产长期观测应同时启用 `pg_stat_statements`，用于从数据库侧确认 top SQL。只执行 `create extension` 还不够；目标 PostgreSQL 还必须在 `postgresql.conf` 或云厂商参数组中配置 `shared_preload_libraries='pg_stat_statements'` 并重启数据库，否则查询会报 `pg_stat_statements must be loaded via shared_preload_libraries`。

启用检查：

```sql
show shared_preload_libraries;
select count(*) from pg_extension where extname = 'pg_stat_statements';
select count(*) from pg_stat_statements;
```

Top SQL 采样：

```sql
select
  calls,
  round(mean_exec_time::numeric, 3) as mean_exec_ms,
  round(total_exec_time::numeric, 3) as total_exec_ms,
  left(regexp_replace(query, '\s+', ' ', 'g'), 200) as query
from pg_stat_statements
where query ilike '%read_model.workbench%'
   or query ilike '%job.read_model_dirty_scopes%'
   or query ilike '%job.outbox_events%'
order by total_exec_time desc
limit 20;
```

`0018_api_performance_read_model.sql` 会执行 `create extension if not exists pg_stat_statements`。如果目标环境的 migrator 没有创建 extension 权限，应由 DBA 预先启用 extension，再执行应用 migration。

## Phase 1.5 读 API 验证

生产和 staging 的工作台列表页使用分层契约，不再把完整 group payload 当作首屏数据：

- `/api/workbench/groups?...&detail_level=summary`：列表和分页使用，响应不得包含行级 `detail_fields`、`raw_payload`、OCR 正文或附件全文。
- `/api/workbench/groups/detail?...&group_id=...`：单个 group 的完整详情，按用户动作懒加载。
- Redis page cache key 必须包含 `detail_level`，避免 summary 和 full payload 互相污染。
- Redis page cache key 必须随 active generation 变化而失效；如果页面显示旧数据，先看 `active_generation_id/read_model_version/generated_at` 是否变化，再看 Redis hit/miss 和版本 key。
- `read_model.workbench_generations` 中同一 `scope_key` 只能有一个 `status='active'`。如果存在 `building_generation_id` 但页面仍显示旧数据，这是正常刷新中；如果存在 `failed_generation_id`，页面仍读取 active generation，同时运维需要处理 `last_error`。
- `/api/workbench/groups` 不带 `detail_level` 时保持 `full`，只作为兼容契约，不作为前端首屏路径。

实时加载判读：

- 页面显示“关联台正在刷新”但已有数据可见：正常，说明前端正在使用最近稳定 read model。
- 页面显示“关联台刷新失败”：查看 `/api/workbench/refresh-status.last_error`、`job.read_model_dirty_scopes.status=failed` 和 worker 日志。
- 页面显示“关联台读模型不可用”：优先检查 PostgreSQL migration、read repository 初始化和生产配置，不要回落旧全量 snapshot。
- 用户只能刷新浏览器才看到新数据：检查 `/api/workbench/events` 是否被代理缓冲或断开，以及前端是否回退轮询 `/api/workbench/refresh-status`。

压测和判定顺序：

```bash
# 1. 在真实 PostgreSQL/Redis 配置下启动 API，并确认 psycopg_pool 已加载。
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.server

# 2. 分别压测 summary、groups summary、group detail、search/cost/tax。
# 记录每个 endpoint 的 p50/p95、平均响应体大小和错误率。

# 3. 读取 /health.api_performance，按 endpoint 对比：
# duration_ms、connection_acquire_ms、sql_execute_fetch_ms、database_query_count。

# 4. 对慢 SQL 单独跑 EXPLAIN (ANALYZE, BUFFERS)，再用 pg_stat_statements 看生产 top SQL。

# 5. 验证同一 generation 下 summary 和 groups 计数稳定，不再随刷新漂移。
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.validate_workbench_generation_convergence \
  --base-url http://localhost:8000 \
  --month all \
  --zone paired \
  --iterations 10 \
  --delay-seconds 1
```

是否进入 Go read API sidecar 只按结果判断。第一阶段和 Phase 1.5 后同时满足以下任意 2 到 3 条，才进入 sidecar 设计：

- `/api/workbench/summary`、`/api/workbench/groups?detail_level=summary`、search/cost/tax 的核心只读 p95 仍高于 300 到 500ms。
- `connection_acquire_ms + sql_execute_fetch_ms` 低于总耗时 30% 到 40%，但整体 p95 仍高。
- Python worker/进程 CPU 持续 70% 到 90% 以上，且 Redis/read model 命中后仍不下降。
- summary 物化和 groups summary 命中后仍慢，瓶颈落在对象构造、JSON 序列化、请求调度或连接并发。
- 水平扩 Python 的机器成本、内存占用或部署复杂度明显高于拆只读 sidecar。

## 收口验证报告

运行时 SQL/read-model 收敛的最终验收报告由以下命令生成：

```bash
PYTHONPATH=backend/src \
python3 -m fin_ops_platform.tools.run_runtime_convergence_closure \
  --json \
  --require-real-infra \
  --run-unit-tests \
  --output /tmp/finops-runtime-convergence-closure-require-real-infra.json
```

报告语义：

- `pass`：该项已在当前环境验证通过。
- `skip`：缺少真实环境或配置；只能用于本地开发报告，不能作为生产验收。
- `fail`：验证失败或强制真实环境下缺少依赖；必须修复后重跑。

生产 cutover 或最终下线旧 snapshot/Mongo/GridFS fallback 前，`--require-real-infra` 报告必须整体为 `pass`。该报告需要覆盖真实 PostgreSQL migration/queue integration、Redis TTL cache、MinIO/S3 checksum smoke、GridFS backfill/verify/orphan cleanup worker、OA Mongo source 只读探测与 `oa.sync` worker、worker `--check` 和 read model 查询性能探测。
