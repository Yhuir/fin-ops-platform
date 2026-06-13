# 监控与告警

## 当前可观察对象

- `/health` 和 app health API。
- `GET /metrics` Prometheus text exposition。
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
- `read_model_refresh_enqueue_to_fresh_ms.p95/p99` 持续升高。该指标从 durable outbox `created_at -> processed_at` 计算，表示真实 enqueue-to-fresh latency，不等同于单次 worker handler duration。
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

## Workbench 索引卫生

Workbench read model 写入会同时维护多张投影表和索引。生产基线中以下索引体积大、`idx_scan=0`，且现有查询不依赖它们的索引类型；`0070_workbench_unused_write_indexes.sql` 会删除它们以降低 active generation 发布写放大：

- `read_model.workbench_rows_payload_gin`
- `read_model.workbench_groups_searchable_text_trgm`
- `read_model.workbench_group_rows_column_values_gin`

保留 `workbench_group_rows_searchable_text_trgm`，因为 pane search 仍有扫描记录。若生产搜索/筛选出现可复现退化，先用 `/health.api_performance`、`EXPLAIN (ANALYZE, BUFFERS)` 和 `pg_stat_user_indexes` 证明相关查询需要恢复索引，再执行回滚 SQL：

```sql
create index if not exists workbench_rows_payload_gin on read_model.workbench_rows using gin (payload);
create index if not exists workbench_groups_searchable_text_trgm on read_model.workbench_groups using gin (searchable_text gin_trgm_ops);
create index if not exists workbench_group_rows_column_values_gin on read_model.workbench_group_rows using gin (column_values);
```

## 日志要求

- 日志应包含请求路径、用户、动作、耗时和错误摘要。
- worker 日志应包含 `queue_event_id`、`event_type`、`attempts`、`trace_id` 和 `source_version`。
- read model API 指标日志使用 `workbench_api_metric`，生产指标系统按 `endpoint` 聚合 p95。
- read model stale/unavailable 计数日志使用 `workbench_read_model_status_metric`，按 `endpoint`、`scope_key`、`read_model_status` 和 `reason` 聚合。
- workbench generation consistency failure 会把 `/api/app-health.workbench_read_model.status` 提升为 `error`，并在 `last_error` 中保留 `generation_metadata_actual_mismatch`、all-scope parent inconsistency、`duplicate_invoice_identity_cross_zone` 或 `duplicate_bank_identity_cross_zone` 原因。
- 工作台实时刷新事件由 `/api/workbench/events` 暴露。SSE 连接失败时前端应回退 `/api/workbench/refresh-status`，运维排障需要同时查看代理是否缓冲 `text/event-stream`、worker lag 和 dirty scope 状态。
- `/health` 输出 `api_performance` 进程内 rolling window 指标，按 `METHOD path` 聚合 `duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_duration_ms` 和 `database_query_count` 的 p50/p95/p99。
- 不输出 token、密码、完整附件正文或敏感原始文件内容。
- 高风险动作需要审计日志，不只依赖应用日志。

## Runtime Queue 指标

`/health` 的 `runtime_infrastructure` 至少包含：

- `queue_backlog`：outbox 当前 backlog/attention status 聚合，不包含历史 `done`。
- `dirty_scopes`：dirty scope 按 status 聚合。
- `oldest_pending_event_age_seconds`：最老 pending event age。
- `worker_heartbeat_lag_seconds`：runtime worker heartbeat lag。
- `worker_metrics`：按中心 registry 展示 required worker 的 heartbeat。没有 heartbeat 的 required worker 显示 `status=missing` / `warning_code=required_worker_missing`；超过该 worker SLO 的显示 `status=stale` / `warning_code=worker_heartbeat_stale`。
- `missing_required_worker_count` / `stale_required_worker_count`：required worker 缺失或 stale 的数量。
- `read_model_refresh_duration_ms`：每类 read model refresh 最近 bounded 样本的 p50/p95/p99，不做全历史排序。
- `read_model_refresh_enqueue_to_fresh_ms`：每类 read model refresh 最近 bounded 样本的 enqueue-to-fresh p50/p95/p99，用于验证“写入后几秒内 fresh”的真实 SLO。
- `read_model_refresh_sample_count`：本次 read model refresh duration/failure rate 使用的 bounded 样本数。
- `read_model_refresh_failure_rate`：同一 bounded 样本内 failed/dead-lettered 比例。
- `read_model_refresh_by_key`：按 read model key / event type 拆分的 bounded refresh duration、enqueue-to-fresh p50/p95/p99、样本数、失败数和失败率，用于定位拖慢总体 p95 的具体 projection。
- `read_model_refresh_current_windows`：按固定窗口 `recent_15m` / `recent_1h` / `recent_6h` 聚合的当前 enqueue-to-fresh 和 duration SLO 口径，用于把当前体验和历史滞留 repair 样本分开。
- `read_model_refresh_by_key_current_windows`：按 read model key / event type / current window 拆分当前 SLO，用于定位当前窗口内仍慢的 projection。
- `read_model_refresh_slow_events`：最近 bounded 样本中最慢的有限条 outbox event 摘要，包含 event/scope/status/source_version/duration/enqueue-to-fresh/skipped 信息；该字段只用于 `/health/ready` drilldown，不把 `event_id` 或 `scope_key` 作为 Prometheus label。
- `read_model_refresh_current_slow_events`：`recent_6h` bounded 样本中最慢的有限条 event/scope 摘要，用于定位当前窗口内具体慢 scope；同样不作为 Prometheus label 导出。
- `stale_dirty_scope_count` 和 `stale_dirty_scopes`：超时 dirty scope 摘要。
- `read_model.workbench_generation_consistency`：active workbench generation 的 metadata、实际 rows/groups 和对象身份跨区一致性。`inconsistent` 必须按 read model unavailable 处理；如果原因是 `duplicate_invoice_identity_cross_zone` 或 `duplicate_bank_identity_cross_zone`，先运行 `python3 -m fin_ops_platform.tools.audit_object_identity --json --workbench-scope <scope>` 定位重复对象，再重建受影响 workbench/workbench_relation scope。
- `redis_hit_count` / `redis_miss_count`：进程内 Redis helper 计数。

RabbitMQ 接入后仍以 PostgreSQL 指标为准；RabbitMQ queue depth 和 DLQ 只能补充投递层健康度，不能代替 outbox/dirty scope 的事实状态。RabbitMQ 相关指标包括：

- `rabbitmq_publish_status`：outbox 按 publish status 聚合。
- `rabbitmq_unpublished_backlog`：等待 dispatcher 投递的 pending outbox 数量。
- `rabbitmq_publish_failed_backlog`：RabbitMQ 发布失败、等待重试的 pending outbox 数量。
- `rabbitmq_dispatcher_lag_seconds`：最老未发布 pending outbox age。
- `rabbitmq_publish_confirm_latency_ms`：每类 RabbitMQ dispatch event 最近 bounded 样本的 publisher confirm p50/p95/p99。
- `rabbitmq_queue_depth`：RabbitMQ workbench queue messages。
- `rabbitmq_unacked_messages`：RabbitMQ unacked delivery 数量。
- `rabbitmq_consumer_count`：RabbitMQ consumer 数量。
- `rabbitmq_dlq_count`：RabbitMQ DLQ 消息数量。
- `rabbitmq_metric_error`：RabbitMQ Management API 不可用或权限错误。

告警建议：

- `rabbitmq_publish_failed_backlog > 0` 且持续 5 分钟。
- `rabbitmq_dispatcher_lag_seconds` 持续超过 worker SLO。5 秒页面同步目标下，dispatcher idle poll 应保持
  `RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.5` 量级；5 秒 poll 会把 outbox-to-broker 等待本身变成 SLO 风险。
- `rabbitmq_queue_depth` 持续增长且 `consumer_count=0`。
- `rabbitmq_unacked_messages` 长时间不下降。
- `rabbitmq_dlq_count > 0`。
- PostgreSQL `failed/dead_lettered` 增长优先级高于 RabbitMQ DLQ，因为 PostgreSQL 才是失败事实。

## Prometheus / Grafana

应用暴露 Prometheus text exposition：

```text
GET /metrics
Authorization: Bearer <FIN_OPS_PROMETHEUS_BEARER_TOKEN>
```

该接口复用 `/health/ready` 的只读 runtime facts，不执行 workbench deep self-test，不新增写入或修复动作。`FIN_OPS_PROMETHEUS_BEARER_TOKEN` 未配置时返回 `404`；配置后必须带同值 bearer token。生产应只允许 Prometheus 从内网或本机端口抓取，不应通过公网代理暴露；即使经过 `/fin-ops-api/` 公网代理，也必须由 token 和代理 ACL 双重保护。

核心指标包括：

- `finops_ready`、`finops_runtime_release_consistent`、`finops_production_runtime_guard_consistent`。
- `finops_outbox_events{status=...}`、`finops_read_model_dirty_scopes{status=...}`、`finops_failed_jobs`、`finops_stale_dirty_scope_count`。
- `finops_read_model_refresh_duration_ms{quantile=...}`、`finops_read_model_refresh_sample_count`、`finops_read_model_refresh_failure_rate`。
- `finops_read_model_refresh_enqueue_to_fresh_ms{quantile=...}`。
- `finops_read_model_refresh_by_key_duration_ms{read_model_key=...,event_type=...,scope_type=...,quantile=...}`、
  `finops_read_model_refresh_by_key_enqueue_to_fresh_ms{read_model_key=...,event_type=...,scope_type=...,quantile=...}`、
  `finops_read_model_refresh_by_key_sample_count{...}`、
  `finops_read_model_refresh_by_key_failure_rate{...}`。
- `finops_read_model_refresh_current_window_enqueue_to_fresh_ms{window=...,quantile=...}`、
  `finops_read_model_refresh_current_window_sample_count{window=...}`。
- `finops_read_model_refresh_by_key_current_window_enqueue_to_fresh_ms{read_model_key=...,event_type=...,scope_type=...,window=...,quantile=...}`、
  `finops_read_model_refresh_by_key_current_window_sample_count{...}`。
- `finops_rabbitmq_queue_depth`、`finops_rabbitmq_dlq_count`、`finops_rabbitmq_consumer_count`、`finops_rabbitmq_publish_confirm_latency_ms{quantile=...}`。
- `finops_worker_heartbeat_lag_seconds{worker_instance=...,worker_kind=...,status=...}`、`finops_worker_required`、`finops_worker_current_effective`。
- `finops_api_duration_ms{endpoint=...,quantile=...}`、`finops_api_connection_acquire_ms{endpoint=...,quantile=...}`、`finops_api_sql_execute_fetch_ms{endpoint=...,quantile=...}`。
- `finops_workbench_read_model_active_scope_count`、`finops_workbench_read_model_active_row_count`、`finops_workbench_read_model_failed_scope_count`。

建议 Grafana 面板至少覆盖：

- read model enqueue-to-fresh / refresh duration p95、failure rate、stale dirty scope count。
- RabbitMQ queue depth、DLQ、consumer count、publisher confirm p95。
- API endpoint p95、DB p95、connection acquire p95。
- worker heartbeat lag、missing/stale/mismatch worker count。
- Redis hit/miss 计数和 PostgreSQL schema/release consistency。

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
- `/health/ready` 和 `/metrics` 的 read model refresh / enqueue-to-fresh / RabbitMQ publish confirm percentile 使用每个 event type 最近 512 条样本，不扫全历史 `done` outbox。
- `read_model_refresh_current_windows` 仍基于每个 event type 最近 512 条 bounded 样本，但按 `created_at` 过滤固定窗口；它用于当前 SLO 判定，历史滞留事件仍由 all-time bounded 指标和 slow events 保留。
- `/health/ready.runtime_infrastructure.read_model_refresh_slow_events` 和 `read_model_refresh_current_slow_events` 用于定位慢 scope；Prometheus 只导出聚合分位数，避免 event/scope 高基数 label。
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

## 同步 SLO 基线采集

生产同步优化阶段使用只读 baseline collector 固化当前证据，避免依赖一次性手工 SQL：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.sync_slo_baseline --json
```

默认采集内容：

- `/health` 同源 PostgreSQL runtime summary、App Status runtime attention、outbox/readiness/worker/RabbitMQ dashboard metrics。
- PostgreSQL 连接数、`max_connections`、连接 state/application 分布。
- `read_model`、`job`、`app` 主要表体积、估算行数和大索引使用情况。
- `pg_stat_statements` top SQL；如果 extension、权限或 `shared_preload_libraries` 不满足，结果会标记 unavailable。
- 关键同步查询的 `EXPLAIN (BUFFERS, FORMAT JSON)`；默认不执行 `ANALYZE`。需要真实执行计划时显式加 `--analyze-explain`，并保存生产变更窗口和回滚说明。

该工具不采集登录态页面 API p95，因为当前 API 性能 recorder 是进程内窗口且 dashboard 接口需要认证。页面首包 p95 必须用登录态 HTTP/browser 采样另行证明，不能用只读 DB baseline 代替。

受控 synthetic read model refresh 使用：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.read_model_slo_smoke --json
```

该工具默认 dry-run，只选择已有 fresh readiness 或 active generation 中的 direct scope；显式加
`--apply` 后才会通过 `ReadModelRefreshGateway` 入队，并等待 outbox event `done` 与
`read_model.app_status_readiness.status='fresh'`，用真实 `created_at -> processed_at` 判断
enqueue-to-fresh 是否满足目标。生产运行必须把 JSON 输出保存到 `/tmp` 或运维归档路径，且在运行后
复核 `/health/ready`、dirty scope、outbox、RabbitMQ DLQ 均收敛。

`--critical-only` 只在未显式传 `--read-model-key` 时按 App Status registry 的 `critical=true`
过滤 smoke scope。它适合先验证当前会阻断页面可用性的 read model；最终全 app 验收仍必须解释
`critical=false` read model 的产品含义，不能用 critical-only 结果代替全量闭环。

## 登录态 HTTP SLO 采样

页面首包和关键读 API p95 使用只读 HTTP probe 采集：

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --iterations 20 \
  --warmup 2 \
  --output /tmp/finops-http-slo-$(date +%Y%m%d%H%M%S).json
```

默认 probe 覆盖：

- `/fin-ops/` 以及主要业务页面 shell：关联台、银行明细、待找发票、进项使用、OA 待付款、销项收款、
  税金抵扣、成本统计、免 OA、批量账务、往来款、ETC、导入、设置和 App Health。只想临时采样单个页面时才显式传
  `--page-path`。
- `/api/session/me`、`/api/app-health`、`/api/operations/app-health-dashboard`。
- 工作台 summary/groups/settings、银行明细账户/流水/规则、待找发票 rows/filter-options/rules、进项发票使用
  rows/filter-options/rules、OA 待付款 rows/filter-options、销项收款 rows/filter-options/rules、税金抵扣、
  成本统计、免 OA、批量账务、往来款、ETC、导入 facts、后台任务和搜索首屏 API。
  `pending-invoices/filter-options` 是历史慢接口，默认必须覆盖。

判定原则：

- 默认目标是每个 probe p95 `< 1000ms`；可用 `--target-ms` 调整单次阶段验收阈值。
- read model API 可接受 `200` 或 `202`，但必须记录响应中的 `read_model_status`、`cache_status` 和 `refresh_enqueued`，用于区分 fresh snapshot、refreshing 和后台追赶。
- 工具默认要求真实认证；没有 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`、`FIN_OPS_HTTP_SLO_BEARER_TOKEN`、`FIN_OPS_HTTP_SLO_COOKIE` 或 CLI auth 参数时返回 `auth_missing`，不能作为生产页面 SLO 证据。
- `--allow-unauthenticated` 只允许做 public page shell smoke，不能用于最终“登录态页面/API p95”验收。
- 输出不包含 token、cookie 或 Authorization header；采样结果可以进入阶段报告和事故复盘。

## Phase 1.5 读 API 验证

生产和 staging 的工作台列表页使用分层契约，不再把完整 group payload 当作首屏数据：

- `/api/workbench/groups?...&detail_level=summary`：列表和分页使用，响应不得包含行级 `detail_fields`、`raw_payload`、OCR 正文或附件全文。
- `/api/workbench/groups/detail?...&group_id=...`：单个 group 的完整详情，按用户动作懒加载。
- Redis page cache key 必须包含 `detail_level`，避免 summary 和 full payload 互相污染。
- Redis page cache key 必须随 active generation 变化而失效；如果页面显示旧数据，先看 `active_generation_id/read_model_version/generated_at` 是否变化，再看 Redis hit/miss 和版本 key。
- `worker-workbench` 发布 active generation 后会预热首屏 `paired/open` page 1 summary 和 Redis version key；如果首个用户仍承担冷启动，按顺序检查 worker 结果中的 `cache_warmup`、Redis `set_text/set_json` 错误、`FIN_OPS_WORKBENCH_GROUPS_REDIS_TTL_SECONDS`、`redis_miss_count` 和 page cache key 的 generation version。
- 普通 read model 的 Redis fresh-cache 必须使用 `ReadModelQueryGateway` 的 fresh-gate envelope：`payload` 之外必须有 `fresh_gate.scope_key`、`fresh_gate.read_model_status=fresh`、`fresh_gate.schema_version` 和 `fresh_gate.source_versions`。命中时 gateway 会按当前 expected source versions 校验；旧格式或 source version 不匹配的 payload 只能 fail closed 回 SQL read model，不能被当作 fresh 返回。
- `/api/workbench/summary` 不应在热路径查询 `app.bank_transactions` 或全量扫描 `read_model.workbench_group_rows` 来修复 counts/diagnostics；summary p95 变慢时先查 `read_model.workbench_summary` active generation 是否缺失，再查 refresh worker 发布失败原因。
- `read_model.workbench_generations` 中同一 `scope_key` 只能有一个 `status='active'`。如果存在 `building_generation_id` 但页面仍显示旧数据，这是正常刷新中；如果存在 `failed_generation_id`，页面仍读取 active generation，同时运维需要处理 `last_error`。
- `read_model.workbench_generations` 的非 active generation 应受 retention 控制。建议告警阈值：总 generation 数超过 300、`read_model.workbench_*` 总大小超过 10GB、根分区可用空间低于 20GB 或 `pg_wal` 异常增长。先检查 `finops-prune-workbench-generations.timer`、自动 retention 日志和 worker 是否持续重复发布同一 scope。
- `/api/workbench/groups` 不带 `detail_level` 时保持 `full`，只作为兼容契约，不作为前端首屏路径。

实时加载判读：

- 页面显示“关联台正在刷新”但已有数据可见：正常，说明前端正在使用最近稳定 read model。
- 页面显示“关联台刷新失败”：查看 `/api/workbench/refresh-status.last_error`、`job.read_model_dirty_scopes.status=failed` 和 worker 日志。
- 页面显示“关联台读模型不可用”：优先检查 PostgreSQL migration、read repository 初始化和生产配置，不要回落旧全量 snapshot。
- 用户只能刷新浏览器才看到新数据：检查 `/api/workbench/events` 是否被代理缓冲或断开，以及前端是否回退轮询 `/api/workbench/refresh-status`。
- 工作台 rebuild profile 中 `_attachment_invoice_rows_from_structured_oa_tables` 退回秒级 JSON 扫描时，先检查 `app.oa_attachment_invoice_cache_sources` 的 `attachment_identity_*` bridge。生产 repair 必须先 dry-run：

```bash
sudo -n /usr/local/sbin/finops-deploy-control workbench-rehydrate <release-name> \
  --repair-attachment-identity-bridge --dry-run --json

sudo -n /usr/local/sbin/finops-deploy-control workbench-rehydrate <release-name> \
  --repair-attachment-identity-bridge --apply-repair --json
```

rollback 只删除可再生的 `source_kind like 'attachment_identity_%'` bridge 行，不删除 OA 附件 cache 本体；仍需先 dry-run：

```bash
sudo -n /usr/local/sbin/finops-deploy-control workbench-rehydrate <release-name> \
  --rollback-attachment-identity-bridge --dry-run --json

sudo -n /usr/local/sbin/finops-deploy-control workbench-rehydrate <release-name> \
  --rollback-attachment-identity-bridge --apply-repair --json
```

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
