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
- `missing_required_worker_count > 0` 或 `stale_required_worker_count > 0`。required worker 清单来自 `runtime_worker_registry`；例如 `search` / `pending-invoice` worker 缺失会导致搜索或待找发票 read model 长时间 refreshing。
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
- `state:full_state` 不应再由 PostgreSQL `PostgresStateStore.save()` 写入。生产 API/worker 不应设置 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1`；若出现该 key 写入，应排查旧工具或未迁移路径。

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
- `/health` / `/health/ready` 输出 bounded `api_performance` 进程内 rolling window 摘要，按 `METHOD path` 聚合 `duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_duration_ms` 和 `database_query_count` 的 p50/p95/p99，但只保留 p95 最慢的有限 endpoint，并通过 `endpoint_count` / `omitted_endpoint_count` 标明是否被截断。完整 endpoint 明细由 `/metrics` 或 admin-only `/api/operations/app-health-dashboard` 提供。
- P2/P3 readiness payload gate 使用 `health_ready_payload_probe` 验证 `/fin-ops-api/health/ready` 本身不成为慢探针：默认要求 1000ms 内、JSON、response 不超过 50KB、`api_performance.endpoints<=20` 且带 `endpoint_count` / `omitted_endpoint_count`；ready payload 只保留 runtime blocker 需要的 counts、status summary 和 bounded problem samples，不输出完整 `entrypoints`、`worker_metrics` 或重复的 `storage.runtime_infrastructure`；慢、大、未截断、缺 metadata 或 HTML fallback 均视为失败。
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
- `read_model.workbench_generation_consistency`：active workbench generation 的 metadata、实际 rows/groups、对象身份跨区一致性和可见 row 归属唯一性。`inconsistent` 必须按 read model unavailable 处理；如果原因是 `duplicate_invoice_identity_cross_zone`、`duplicate_bank_identity_cross_zone` 或 `duplicate_row_membership`，先运行 `python3 -m fin_ops_platform.tools.audit_object_identity --json --workbench-scope <scope>` 定位重复对象，再重建受影响 workbench/workbench_relation scope。发布前也要用同一审计命令确认 `workbench_open_visible_owner_duplicate_group_count=0`；同一命令的 `blocking_issue_count` 只计入强发票 identity、银行 identity、OA 附件强 identity、Workbench 归属和 active relation orphan 风险，弱税额指纹与 `app.etc_invoices` 原始来源重复只作为 warning。
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

### Workbench 自动决策污染修复

当关联台出现 `oa_bank_exact_sum` 把弱文本证据、OA 项目/申请人 token、已被 active relation 占用的 row，或已被 submitted no-OA batch 闭环的银行流水拼成候选时，必须先确认生成规则和 cleanup dry-run 判定已修复，再清理旧 decision；只删页面缓存或手工改一条 SQL 会被下一次 matching upsert 或 read model rebuild 污染回来。

dry-run：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.repair_workbench_reconciliation_decisions \
  --scope 2026-02 \
  --json
```

dry-run 的 `plan.items[].reasons[].code` 至少应明确命中一种已知污染原因，例如：

- `active_relation_row_overlap`：decision 复用 active Workbench relation 已占用 row。
- `submitted_no_oa_batch_row_overlap`：decision 复用 submitted no-OA batch 中的银行流水，即使对应 relation snapshot 已被取消或滞后也必须清理旧 decision。
- `weak_only_oa_bank_sum_evidence`：`oa_bank_exact_sum` 只由弱 token 或 OA 项目/申请人来源 token 支撑。

执行清理：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.repair_workbench_reconciliation_decisions \
  --scope 2026-02 \
  --execute \
  --reason invalid_oa_bank_exact_sum_cleanup_2026_06_14 \
  --json
```

执行清理必须通过 repair 工具或同等 service/repository 边界完成。工具会在同一事务内 expire
无效 decision，并补投受影响月份的 `workbench` 与 `workbench_relation` read model refresh；不要绕过
source-version guard 直接改表。若历史上已用旧版本工具执行过 expire，导致 dry-run 已归零但月度
active generation 仍保留旧 `case:decision:*` open 组，应先通过既有 read model refresh gateway/queue
补投该月份 `workbench` scope，再重建页面 projection。

清理后重建受影响 Workbench generation，并让 `all` 从 active shards 重新聚合：

```bash
PYTHONPATH=backend/src python3 scripts/rehydrate-workbench-read-models.py \
  --scope 2026-02 \
  --scope 2026-03 \
  --json
```

如果 relation facts 也发生变更，再通过既有 runtime queue/backfill 入口刷新下游 `workbench_relation`、`bank_detail`、`cost_statistics`、`search` 等 scope；仅清理 reconciliation decision 时，不要直接改 `app.workbench_pair_relations` 中正确的 no-OA/internal-transfer relation，也不要为了让 cleanup 命中而手工改 submitted no-OA batch。

告警建议：

- `rabbitmq_publish_failed_backlog > 0` 且持续 5 分钟。
- `rabbitmq_dispatcher_lag_seconds` 持续超过 worker SLO。一秒级页面同步目标下，dispatcher idle poll 应保持
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

- `数据`：`app.bank_transactions`、`app.invoices`、`app.oa_applications`、`app.oa_application_items` 的数量和最近同步时间。发票来源只拆为 `手工导入` 和 `OA 解析`；`OA 解析` 括号内数量表示 OA 解析来源且不在手工导入中的发票数。主页面还展示最新 5 条流水、手工发票、OA 解析和 OA 单据同步历史，右侧抽屉展示全量历史。
- `请求`：当前 API 进程内 rolling window 的 p95/p99，包括完整请求耗时、DB 总耗时、连接获取、SQL execute/fetch 和 SQL 次数。
- `后台`：`job.outbox_events`、RabbitMQ queue/DLQ、`job.runtime_worker_heartbeats`、read model refresh duration 和 dirty scope 计数。

Dashboard API 使用短 TTL 进程内缓存，默认 30 秒，可通过 `FIN_OPS_APP_HEALTH_DASHBOARD_CACHE_TTL_SECONDS` 调整。缓存过期后刷新失败时，接口返回上一份 payload，并在 `freshness.warnings` 中加入 `dashboard_cache_stale_after_error`；权限校验和 PostgreSQL runtime 缺失不走缓存兜底。

判读原则：

- `--` 表示 unknown 或当前无可靠样本，不等于 0。
- RabbitMQ 指标缺失时仍以 PostgreSQL outbox/dirty scopes 为准。
- API/DB p95 同时升高，优先看 PostgreSQL、连接池和 top SQL。
- API p95 升高但 DB 指标不高，优先看 Python 对象构造、JSON 序列化、前端请求量和网络。
- 发票 inventory 读取 canonical `app.invoices.source_links`：`manual_invoice_import` 计入 `手工导入`，`oa_attachment_invoice` 计入 `OA 解析`，同时带 `oa_attachment_invoice` 但不带 `manual_invoice_import` 的 active 发票计入 OA 括号数。OA 附件 OCR cache 只是解析缓存，不作为 App Health 发票 inventory 事实源；ETC 已包含在手工导入口径中，不单独展示。
- 导入历史数量来自真实成功导入/同步事实：流水和手工发票读取 `app.import_batches.success_count`，OA 解析读取 canonical invoice OA source links，OA 单据同步读取 `app.oa_sync_runs(sync_type='oa_projection').upserted_count`。预览候选数、附件数和 OCR 候选项总数不得作为导入数量。
- Read model refresh 的“历史”指标是 bounded history：最近 7 天或每个 event type 最近 512 条完成事件，不是全库永久历史扫描。
- `/health/ready` 和 `/metrics` 的 read model refresh / enqueue-to-fresh / RabbitMQ publish confirm percentile 使用每个 event type 最近 512 条样本，不扫全历史 `done` outbox。
- `read_model_refresh_current_windows` 仍基于每个 event type 最近 512 条 bounded 样本，但按 `created_at` 过滤固定窗口；它用于当前 SLO 判定，历史滞留事件仍由 all-time bounded 指标和 slow events 保留。
- `/health/ready.runtime_infrastructure.read_model_refresh_slow_events` 和 `read_model_refresh_current_slow_events` 用于定位慢 scope；Prometheus 只导出聚合分位数，避免 event/scope 高基数 label。
- read model refresh 指标查询必须使用 bounded partial indexes；`outbox_events_read_model_refresh_metric_attention_idx` 覆盖 completed duration rows 与 failed/dead-lettered rows，避免 full health/dashboard 在大 outbox 表上因 `done OR failed` 样本条件退化为历史扫描。
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
enqueue-to-fresh 是否满足目标。`summary.enqueue_to_fresh_ms` 会输出 p50/p95/p99/max，最终 P2/P3 gate
必须用 p95 `<= 1000ms` 解读，而不是只看单个最快样本。生产运行必须把 JSON 输出保存到 `/tmp` 或运维归档路径，且在运行后
复核 `/health/ready`、dirty scope、outbox、RabbitMQ DLQ 均收敛。

最终 closure 不能接受空样本：`--apply` 报告必须有 `planned_scope_count > 0`、`result_count > 0`，
且 `failed_count = 0`。如果报告返回 `no_smoke_scopes_discovered` 或 runtime gate 返回
`read_model_smoke_empty_samples`，先修 registry/scope selection 或显式传入 `--read-model-key` / `--scope`，
不要把零样本当作 worker SLO 通过。

`--critical-only` 只在未显式传 `--read-model-key` 时按 App Status registry 的 `critical=true`
过滤 smoke scope。它适合先验证当前会阻断页面可用性的 read model；最终全 app 验收仍必须解释
`critical=false` read model 的产品含义，不能用 critical-only 结果代替全量闭环。

## 生产外部 Gate 输入预检

生产 admin Browser smoke、authenticated HTTP/SSE SLO 和 controlled write-operation apply 依赖真实登录态、
管理员凭据、数据库连接、写操作 scenario 和审批 ticket。执行这些 gate 前先运行：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --json
```

预检输出只包含 gate 状态、缺失的 env 名称和 `secret_values_redacted=true`，不输出 token、cookie、数据库 URL
或 scenario 文件内容。需要无人值守脚本在缺少输入时失败时，使用：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --require-ready
```

退出码约定：

- `0`：所有外部 gate 的本地输入已配置；仍需由各 gate 自己证明 token 权限、页面/API 正常和 SLO 达标。
- `2`：至少一个 gate 缺少 token、cookie、scenario、数据库连接或审批 ticket；这应标记为
  `external_input_required`，不是产品代码失败。

特别注意：`write_operation_apply` 只有在同时具备真实认证、PostgreSQL URL、安全隔离 scenario 和
`FIN_OPS_WRITE_E2E_APPROVAL_TICKET` 时才允许执行。生产 mutating smoke 必须可回滚、范围明确，并保留审批记录。

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

- 默认目标是每个 probe p95 `<= 1000ms`；可用 `--target-ms` 调整单次阶段验收阈值。
- read model API 可接受 `200` 或 `202`，但必须记录响应中的 `read_model_status`、`cache_status` 和 `refresh_enqueued`，用于区分 fresh snapshot、refreshing 和后台追赶。
- 工具默认要求真实认证；没有 `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`、`FIN_OPS_HTTP_SLO_BEARER_TOKEN`、`FIN_OPS_HTTP_SLO_COOKIE` 或 CLI auth 参数时返回 `auth_missing`，不能作为生产页面 SLO 证据。
- 工具默认发送 `Accept-Encoding: gzip`，用于对齐真实浏览器经过 Nginx 的传输口径；JSON/HTML 解析会先解压 gzip body，`response_bytes` 记录压缩后的网络传输字节数。生产公网性能判断应使用该默认口径，避免用未压缩的大 JSON 传输时间误判浏览器首屏 SLO。
- API probe 如果拿到 `text/html` 或 HTML 文档体，即使 HTTP status 是 200，也按 `html_response_for_api_probe` 失败处理。这通常表示 API prefix、Nginx fallback 或路径配置错误；例如 `www.yn-sourcing.com/health/ready` 会落到前端页面壳，生产 readiness 应使用 `/fin-ops-api/health/ready`。
- Readiness payload 单独用只读 probe 验证，不需要登录态：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.health_ready_payload_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --target-ms 1000 \
  --output /tmp/finops-health-ready-payload-$(date +%Y%m%d%H%M%S).json
```

- `--allow-unauthenticated` 只允许做 public page shell smoke，不能用于最终“登录态页面/API p95”验收。
- 只做 public page shell smoke 时必须同时传 `--replace-default-probes`，否则默认 API probes 会一起执行并因未登录返回 401，导致整体报告失败。示例：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --allow-unauthenticated \
  --replace-default-probes \
  --iterations 3 \
  --warmup 1 \
  --target-ms 1000 \
  --output /tmp/finops-public-page-shell-$(date +%Y%m%d%H%M%S).json
```
- 输出不包含 token、cookie 或 Authorization header；采样结果可以进入阶段报告和事故复盘。

## SSE 首事件 Smoke

App Health 和 Workbench 依赖 SSE 做运行状态/刷新状态提示。P2/P3 中 Nginx/OA iframe/SSE buffering 不能只靠页面 shell 或普通
HTTP probe 证明，使用只读 `sse_smoke_probe` 验证 event-stream 首事件：

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.sse_smoke_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --target-ms 1000 \
  --output /tmp/finops-sse-smoke-$(date +%Y%m%d%H%M%S).json
```

默认 probe 覆盖：

- `/api/app-health/stream`：期望 `event: app_health` 或 `event: heartbeat`。
- `/api/workbench/events?month=all`：期望 `event: workbench.read_model.*` 或 `event: heartbeat`。

判定原则：

- 默认目标是首个 SSE event `<= 1000ms`；超过目标返回 `sse_first_event_slo_miss`。
- 缺少 token/cookie 返回 `auth_missing`，不能作为生产 SSE 证据。
- 返回 HTML 页面壳按 `html_response_for_api_probe` 失败；这通常表示 API prefix 或 Nginx fallback 配置错误。
- 返回非 `text/event-stream`、没有 `event:` 行或事件名不匹配均失败；失败时先区分 auth、proxy buffering、API prefix、后端 route 和 worker/readiness 源头。
- 输出不包含 token、cookie 或 Authorization header。

## 真实写操作刷新 SLO 审计

`read_model_slo_smoke` 证明 worker 对受控 direct scope 的处理能力；它不证明每个真实写入口都正确写入 dirty scope/outbox。
真实写操作链路使用 durable outbox 历史审计：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --lookback-hours 24 \
  --target-ms 1000 \
  --p99-target-ms 3000 \
  --output /tmp/finops-write-operation-slo-$(date +%Y%m%d%H%M%S).json
```

默认 profile 覆盖当前高影响写操作的 read model refresh 事件：

- `turnover_manual_closure_or_withdraw`：`turnover_relation_changed` 必须覆盖 `turnover_ledger`、`workbench`、
  `workbench_relation`、`cost_statistics`、`search`，并匹配 `turnover_relation_zero_difference_closure`、
  `withdraw_relation` 或 `turnover_relation_withdraw` action metadata。
- `turnover_relation_extra`、`turnover_tag_selection`：必须刷新 `turnover_ledger`。
- `bank_row_tags_batch`：必须覆盖银行明细、关联台和往来款相关 refresh，并匹配 bank row tags action metadata。
- `bank_auto_tag_rules`、`bank_category_confirmation`、`no_oa_tag_selection`：必须能在 durable outbox 中看到对应
  read model refresh。

判定原则：

- 工具只读 `job.outbox_events` 和 `job.read_model_dirty_scopes`，不会发起业务写操作。
- 每个 required expectation 必须在 lookback window 内有真实样本；没有样本返回 `missing`，不能当作通过。
- 最终闭环要求 `event_sample_count > 0`、`expectation_count > 0`、`failed_expectation_count = 0` 且
  `missing_expectation_count = 0`。如果 runtime gate 返回 `write_operation_audit_empty_samples`，表示缺少真实 durable
  write 证据，应生成或审批受控写 scenario 后复跑，而不是把空样本当成性能通过。
- 新发布后的 turnover UoW 事件会把非敏感 `action_name` 写入 outbox payload；工具会用它区分共享同一 reason 的不同写操作。
- 样本必须 `event_status=done`，dirty scope 必须为空或 `done`，且 p95 enqueue-to-done `<= target-ms`、p99
  enqueue-to-done `<= p99-target-ms`。P2/P3 一秒级闭环默认使用 p95 `1000ms`、p99 `3000ms`。
- 该工具能证明“最近真实写操作产生的 refresh 是否及时完成”，但不能证明没有被执行过的操作；最终闭环仍需要受控
  E2E 写操作 smoke 覆盖关联、撤回、导入确认和规则变更。

## 受控写操作 E2E SLO Smoke

真实写操作闭环使用 `write_operation_e2e_smoke` 执行。该工具默认只校验 scenario 并输出计划；只有显式 `--apply`、存在真实认证 header/cookie，且提供业务审批引用 `--approval-ticket` / `FIN_OPS_WRITE_E2E_APPROVAL_TICKET` 时才会发起 mutating HTTP 请求。

scenario 文件示例：

```json
{
  "scenarios": [
    {
      "name": "turnover-withdraw-smoke",
      "operation": "turnover_manual_closure_or_withdraw",
      "steps": [
        {
          "name": "withdraw",
          "method": "POST",
          "path": "/api/workbench/actions/withdraw-link",
          "json": {
            "month": "2026-02",
            "row_ids": ["<bank_row_id>", "<oa_or_turnover_row_id>"],
            "idempotency_key": "write-smoke-turnover-<case_id>",
            "reason": "controlled SLO smoke"
          },
          "expected_statuses": [200]
        }
      ],
      "post_api_probes": [
        {
          "name": "turnover_ledger_grouped",
          "path": "/api/turnover-ledger?view=grouped&page=1&page_size=50",
          "expected_statuses": [200, 202],
          "target_ms": 1000
        }
      ]
    }
  ]
}
```

生产标准输入：

- 标准 scenario 文件：`/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`
- 标准审批引用：`FINOPS-WRITE-SMOKE-STANDING-20260702`
- 标准 env：
  - `FIN_OPS_WRITE_E2E_SCENARIO=/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`
  - `FIN_OPS_WRITE_E2E_APPROVAL_TICKET=FINOPS-WRITE-SMOKE-STANDING-20260702`

标准 scenario 文件由只读 discovery 生成，不把生产业务 ID 写入仓库：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_scenario_discovery \
  --limit 1 \
  --scenario-output "$FIN_OPS_WRITE_E2E_SCENARIO" \
  --output /tmp/finops-write-scenario-discovery-$(date +%Y%m%d%H%M%S).json
chmod 600 "$FIN_OPS_WRITE_E2E_SCENARIO"
```

如果某一类没有满足安全边界的候选，标准文件可以少于 3 个 scenario；主控 workflow 应记录该类候选缺失并准备可回滚测试对象，
不得为了凑齐数量回退到旧 API 路径、宽泛 SQL 选择或真实待处理业务对象。

页面 / 模块 write scenario 与 approval ticket 矩阵：

该矩阵同时写入 `write_operation_scenario_discovery` 的 `page_write_scenario_policy` 和生成的 scenario JSON；
主控 workflow 必须读取该矩阵，不再为标准 production smoke 逐次询问 scenario 或 approval ticket。若某类没有安全候选，记录为候选缺失并准备可回滚测试对象，
禁止回退旧 API、宽泛 SQL 或真实待处理业务对象。

| 页面 / 模块 | Apply policy | 标准写场景 | Approval ticket | 说明 |
| --- | --- | --- | --- | --- |
| 往来款 | `standing_apply` | `turnover_manual_closure_or_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 只选择已有 active Workbench relation 承载的手工往来闭环，并通过 `/api/workbench/actions/withdraw-link` 撤回；不走旧的 turnover relation 直连撤回路径。 |
| 关联台 / Workbench relation | `standing_apply` | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 只选择 `manual_confirmed` active relation，要求有明确月份且成员行数 bounded，覆盖 workbench/workbench_relation 及跨页 fan-out。 |
| 免 OA 流水批次 | `standing_apply` | `no_oa_bank_batch_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 只选择 submitted 且有明确 scope month 的批次，要求银行流水成员 bounded，覆盖 no-OA、workbench、cost/search fan-out。 |
| 流水规则批量处理 | `fanout_evidence` | `no_oa_bank_batch_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 不新增独立生产写入；通过 no-OA/bank-flow fan-out、direct read model smoke 和页面 API SLO 证明。 |
| 银行明细 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用上游可逆 withdraw 的 affected scopes、direct read model smoke、authenticated HTTP/SSE 和 audit 证明；不伪造银行明细独立生产 mutation。 |
| 银行账户余额 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用银行事实源 fan-out 与 all-only read model smoke 证明。 |
| 待找发票 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用上游关联撤回影响的 pending scope 和 read model/API SLO 证明。 |
| 进项发票使用情况 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用 workbench/no-OA/turnover fan-out 和 invoice usage worker 证明。 |
| 销项发票收款情况 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用 fan-out、direct read model smoke 和 post API probe 证明。 |
| 发票生命周期 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用关联撤回后的 lifecycle affected scope 证明。 |
| OA 待付款 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 生产 smoke 不自动写 OA 付款状态；页面显式写回必须由 OA 写回配置和单独业务流程控制。 |
| 税金抵扣 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用成本/发票 fan-out、read model smoke 和页面 API SLO 证明。 |
| 成本统计 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用 Workbench active generation fan-out、成本统计 read model smoke 和页面 API SLO 证明。 |
| 搜索 | `fanout_evidence` | 三类 standing write 场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用各写入链路的 search refresh fan-out、direct read model smoke 和 search API SLO 证明。 |
| 批量账务 | `fanout_evidence` | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用 Workbench relation fan-out 与批量账务查询 read model 证明，不新增独立 production apply。 |
| 导入：银行流水 / 发票 / ETC | `no_standing_production_apply` | 无 | 无 standing ticket | 只能 staging 或单次审批的可回滚 scenario；不得用 standing approval 自动执行导入写入。 |
| 设置 | `no_standing_production_apply` | 无 | 无 standing ticket | 设置写入会改变系统口径或权限，只能 staging 或单次审批。 |
| 数据重置 | `no_standing_production_apply` | 无 | 无 standing ticket | destructive/reset 操作禁止使用 standing production smoke。 |

dry-run：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_e2e_smoke \
  --scenario "$FIN_OPS_WRITE_E2E_SCENARIO" \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api
```

apply：

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_e2e_smoke \
  --scenario "$FIN_OPS_WRITE_E2E_SCENARIO" \
  --apply \
  --approval-ticket "$FIN_OPS_WRITE_E2E_APPROVAL_TICKET" \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --write-target-ms 1000 \
  --http-target-ms 1000 \
  --output /tmp/finops-write-e2e-slo-$(date +%Y%m%d%H%M%S).json
```

说明：`write_operation_scenario_discovery --limit 1` 用来生成每类 operation 最多 1 条最小闭环 scenario；
`write_operation_e2e_smoke` 的写后 SLO 事件读取会按当前 scenario 的 operation expectation 过滤 outbox，并保持有效采样窗口下限。
因此主控 workflow 可以继续使用最小 scenario 输入，不会因为 `--limit 1` 漏掉同一写事务内稍晚完成的必需 read model refresh。

执行前要求：

- scenario 必须使用可控测试对象或已确认可回滚的业务对象；不要直接对生产真实待处理业务做破坏性测试。
- `--apply` 必须带审批引用；缺少 `--approval-ticket` / `FIN_OPS_WRITE_E2E_APPROVAL_TICKET` 会返回 `status=approval_missing`，且不会连接 Postgres 或发起 mutating HTTP。
- 每个 mutating step 必须有预期状态码；工具不会把 409/403/500 继续包装成已同步。
- mutating step 如果拿到 `text/html` 或 HTML 页面壳，即使状态码匹配，也会按 `html_response_for_api_probe` 失败并跳过 write SLO claim；这通常表示 API prefix、Nginx fallback 或路径配置错误。
- 写步骤成功后，工具以数据库 `clock_timestamp()` 为起点，等待对应 operation profile 的 outbox/dirty scope 达到 p95
  `1000ms` / p99 `3000ms` SLO。
- post API probe 只用于验证写后页面首屏 API；最终仍要结合登录态 HTTP SLO、App Health 和审计记录。
- 输出不包含 token、cookie、Authorization header，也不输出 scenario 请求 body，只记录路径、状态码、耗时和 outbox/readiness 结果。

## 全 App 同步闭环 Gate

最终闭环使用 `runtime_sync_closure_gate` 聚合检查，避免把 direct smoke、页面 shell 或历史 audit 中任意单项误判为“全 app 已闭环”。

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
export FIN_OPS_WRITE_E2E_SCENARIO=/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json
export FIN_OPS_WRITE_E2E_APPROVAL_TICKET=FINOPS-WRITE-SMOKE-STANDING-20260702
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --apply-read-model-smoke \
  --write-scenario "$FIN_OPS_WRITE_E2E_SCENARIO" \
  --apply-write-scenarios \
  --write-approval-ticket "$FIN_OPS_WRITE_E2E_APPROVAL_TICKET" \
  --http-target-ms 1000 \
  --sse-target-ms 1000 \
  --health-ready-target-ms 1000 \
  --read-model-target-ms 1000 \
  --write-target-ms 1000 \
  --output /tmp/finops-runtime-sync-closure-gate-$(date +%Y%m%d%H%M%S).json
```

该 gate 必须全部通过才可宣称“所有页面一秒级真同步”：

- runtime health：required worker、RabbitMQ queue/unacked/DLQ、dirty scope、failure rate 没有当前 blocker。
- health-ready payload：`/fin-ops-api/health/ready` 自身在 1000ms 内返回轻量 JSON，`api_performance` bounded 且带截断 metadata。
- direct read model smoke：显式 `--apply-read-model-smoke` 后，每个 App Status read model 的 enqueue-to-fresh 在目标内。
- 登录态 HTTP SLO：必须使用真实 OA token/Admin-Token/cookie，覆盖全 app 页面 shell 与首屏 API p95。
- 登录态 SSE smoke：必须使用真实 OA token/Admin-Token/cookie，覆盖 App Health 和 Workbench event-stream 首事件 `<= 1000ms`，并拒绝 HTML fallback 或错误事件名。
- 真实写操作 audit：最近真实 durable outbox 样本覆盖内置高影响 operation profile，并满足写入后 outbox done SLO。
- 受控写操作 E2E：必须提供安全、可回滚的 scenario，并显式 `--apply-write-scenarios` 和 `--write-approval-ticket` 通过 mutating HTTP + 写后 outbox/readiness + 可选 post API。

缺少真实认证、缺少 scenario、只 dry-run、缺少审批引用、invalid scenario、runtime health 缺事实字段、或 write audit 没有样本时，gate 会返回 `fail`。
Postgres-backed gates 在缺少 `FIN_OPS_POSTGRES_DATABASE_URL` / `DATABASE_URL` 时会返回
`status=configuration_missing`、`blocking_condition=database_url_required`、`required_env`、
安全 `next_actions`、`allowed_remote_evidence` 和 `forbidden_without_approval`。这表示需要在安全运行环境
配置 DB URL，或进入批准的生产只读采样分支；不能把它改成 `pass`、`skip` 或一秒级 SLO 证据。
runtime health 没有 durable queue、dirty scope、required worker 或 refresh failure facts 时，`runtime_health` check
会返回 `runtime_health_missing_facts`，不能作为 worker/readiness/queue 收敛证据。
health-ready payload 慢、大、未截断、缺 `endpoint_count` / `omitted_endpoint_count` 或 HTML fallback 时，
`health_ready_payload` check 会返回 fail；这通常表示 bounded readiness fix 未部署、API prefix/Nginx fallback 错误，
或 readiness endpoint 本身已经成为慢探针。
单独的 `health_ready_payload_probe` 还会输出 `runtime_release_name`、`runtime_blocker_count` 和
`runtime_blockers`。这些字段用于在不登录服务器的第一步区分 release 未部署、dirty/outbox backlog、
failed jobs、worker mismatch、Postgres/readiness 状态异常或 runtime guard 问题；`dirty_scopes.done`
等完成态计数不应被当作 blocker。
HTTP SLO 没有 probe/sample 时，`authenticated_http_slo` check 会返回 `http_slo_empty_samples`；SSE smoke
没有 probe 时，`sse_first_event_smoke` check 会返回 `sse_smoke_empty_samples`。这通常表示 probe 配置、认证、
API prefix 或采样输入错误，不能作为一秒级证据。
缺少受控写 E2E 参数时，`write_operation_e2e` check 会暴露 `missing_args` / `required_args`；scenario 文件存在但
不可用时，`write_operation_audit` 和 `write_operation_e2e` 会返回 `input_error`，不会退回运行 unscoped write audit。
直接调用 `write_operation_e2e_smoke` 时，空 scenario list 返回 `input_error` / `scenario_empty`，不能作为 dry-run
或 apply 成功。
受控写 E2E apply 后没有 scenario/result 样本时，`write_operation_e2e` check 会返回
`write_operation_e2e_empty_samples`，不能作为真实 mutating 写入证据。
write audit 没有真实 event/expectation 样本时，`write_operation_audit` check 会返回
`write_operation_audit_empty_samples`。
主控 workflow 应据此分流到 scenario 生成、输入修复、审批或 apply。上述失败是预期行为，不应改成 `pass` 或
`skip` 来绕过最终验收。

## 写操作 Scenario 发现

`write_operation_scenario_discovery` 是只读工具，用于从 PostgreSQL 事实表生成可审核的
`write_operation_e2e_smoke` scenario 草稿。

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_scenario_discovery \
  --output /tmp/finops-write-operation-scenario-discovery-$(date +%Y%m%d%H%M%S).json \
  --scenario-output /tmp/finops-write-e2e-scenarios-$(date +%Y%m%d%H%M%S).json
```

边界：

- 工具只读，不发 mutating HTTP，也不写数据库。
- 默认把已被 write-operation audit profile 覆盖的 `turnover_manual_closure_or_withdraw`、`workbench_relation_withdraw`
  和 `no_oa_bank_batch_withdraw` 候选写入 scenario。
- 生产标准使用 `--limit 1` 生成最小闭环输入，避免 full gate 串行执行过多生产写步骤。
- `turnover_manual_closure_or_withdraw` 只选择 active Workbench relation 支撑的手工往来闭环，要求成员行数在 `2..6`
  且有明确月份；scenario 必须调用 `/api/workbench/actions/withdraw-link`，禁止把旧
  `/api/turnover-ledger/relations/{id}/withdraw` 直连路径作为 standing smoke。
- `workbench_relation_withdraw` 只选择 `manual_confirmed` active relation，要求成员行数在 `2..6` 且有明确月份。
- `no_oa_bank_batch_withdraw` 只选择 submitted 批次，要求 `scope_month` 非空且 `bank_transaction_ids` 数量在
  `1..6`，优先选择月份内批次数少的候选。
- 如果没有发现候选，报告返回 `status=no_candidates`，即使传了 `--scenario-output` 也不会写空 scenario 文件；主控
  workflow 应先准备已审批、可回滚的测试对象，再重新 discovery。
- 生成的 scenario 仍需要人工确认测试对象、业务影响和回滚路径；不能直接对真实待处理业务盲目 `--apply`。

## Phase 1.5 读 API 验证

生产和 staging 的工作台列表页使用分层契约，不再把完整 group payload 当作首屏数据：

- `/api/workbench/groups?...&detail_level=summary`：列表和分页使用，响应不得包含行级 `detail_fields`、`raw_payload`、OCR 正文或附件全文。
- `/api/workbench/groups/detail?...&group_id=...`：单个 group 的完整详情，按用户动作懒加载。
- Redis page cache key 必须包含 `detail_level`，避免 summary 和 full payload 互相污染。
- Redis page cache key 必须随 active generation 变化而失效；如果页面显示旧数据，先看 `active_generation_id/read_model_version/generated_at` 是否变化，再看 Redis hit/miss 和版本 key。
- `worker-workbench` 默认不把 Redis page-cache warmup 放进 refresh ack 前热路径；页面仍从 fresh SQL read model 读取，API 读路径只在 fresh gate 后写 Redis payload。只有显式设置 `FIN_OPS_WORKBENCH_GROUPS_SYNC_CACHE_WARMUP_ENABLED=1` 时才同步预热首屏 `paired/open` page 1 summary 和 Redis version key。若首个用户承担冷启动，按顺序检查 Redis `set_text/set_json` 错误、`FIN_OPS_WORKBENCH_GROUPS_REDIS_TTL_SECONDS`、`redis_miss_count` 和 page cache key 的 generation version。
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
- OA 附件正式发票在 Workbench/税金中缺失时，先检查是否已 promotion 到 `app.invoices` 且 `raw_payload.source_links[].source_type='oa_attachment_invoice'`；再检查 `app.oa_attachment_invoice_cache_sources` 的 `attachment_identity_*` bridge 是否能把 parser cache 映射回真实附件。生产 repair 必须先 dry-run：

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

## 收口验证

旧 `run_runtime_convergence_closure` 高权限收敛工具已删除，不能再作为生产验收入口。运行时验证改用当前分项 gate：`scripts/verify.sh runtime-check`、RabbitMQ staging preflight、deploy examples tests、worker `--check`、read model/API 性能探测和对应模块测试。
