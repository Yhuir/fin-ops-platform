# 监控与告警

## 当前可观察对象

- `/health` 和 app health API。
- `GET /metrics` Prometheus text exposition。
- `GET /api/operations/app-health-dashboard` 管理员只读 Dashboard。
- OA 同步状态。
- 后台任务状态。
- Runtime durable outbox backlog、failed/dead-letter outbox event、required worker heartbeat 和 RabbitMQ 投递层状态。
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
- `worker_heartbeat_lag_seconds` 持续超过 worker poll interval 与任务超时阈值。
- `missing_required_worker_count > 0` 或 `stale_required_worker_count > 0`。required worker 清单来自 `runtime_worker_registry`；required worker 缺失影响真实后台任务，不代表页面 legacy projection 同步状态。
- `/api/workbench`、`/api/workbench/summary` 或 `/api/workbench/groups` 的 `workbench_api_metric.duration_ms` p95 超过页面 direct API SLO。
- Workbench direct API 或 App Health 长时间显示 `failed` / `unavailable`，或 matching worker heartbeat/backlog 异常。
- `/health.api_performance.endpoints[*].duration_ms.p95` 持续超过页面 SLO。
- `/health.api_performance.endpoints[*].connection_acquire_ms.p95` 持续升高，表示 PostgreSQL 连接池等待、连接建立或数据库连接资源压力。
- `/health.api_performance.endpoints[*].sql_execute_fetch_ms.p95` 持续升高，表示 SQL 执行/取数本身变慢。
- Redis `redis_miss_count` 快速增长且 PostgreSQL 热读压力同步升高。
- 数据重置任务异常结束。
- 工作台 direct API 长时间无法返回或 direct payload profile 持续退化。
- 非页面兼容 API 或后台诊断返回 `read_model_unavailable` 时，只作为 legacy 删除清单排障；页面 GET 不应依赖该状态，优先检查 direct API、PostgreSQL 连接和 migration 版本。
- `state:full_state` 在 PostgreSQL `app.app_settings` 中持续更新。生产 API/worker 不应设置 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1`；若出现该 key 写入，应排查是否误用了 migration/shadow/test 配置。

## Workbench 索引卫生

Legacy Workbench projection 写入曾同时维护多张投影表和索引。生产基线中以下索引体积大、`idx_scan=0`，且当前 direct query workload 不依赖它们的索引类型；`0070_workbench_unused_write_indexes.sql` 删除它们以降低旧投影写放大：

- `read_model.workbench_rows_payload_gin`
- `read_model.workbench_groups_searchable_text_trgm`
- `read_model.workbench_group_rows_column_values_gin`

保留 `workbench_group_rows_searchable_text_trgm` 只属于历史兼容判断。若生产搜索/筛选出现可复现退化，先用 `/health.api_performance`、`EXPLAIN (ANALYZE, BUFFERS)` 和 `pg_stat_user_indexes` 证明当前 direct 查询需要索引，再执行显式 migration；不要把旧投影索引作为默认回滚动作：

```sql
create index if not exists workbench_rows_payload_gin on read_model.workbench_rows using gin (payload);
create index if not exists workbench_groups_searchable_text_trgm on read_model.workbench_groups using gin (searchable_text gin_trgm_ops);
create index if not exists workbench_group_rows_column_values_gin on read_model.workbench_group_rows using gin (column_values);
```

## 日志要求

- 日志应包含请求路径、用户、动作、耗时和错误摘要。
- worker 日志应包含 `queue_event_id`、`event_type`、`attempts`、`trace_id` 和 `source_version`。
- Workbench direct API 指标日志使用 `workbench_api_metric`，生产指标系统按 `endpoint` 聚合 p95。
- Workbench active-generation stale/unavailable 计数只作为 legacy 存储迁移诊断；页面 GET 不再消费 page read-model 同步状态。
- Workbench page read-model SSE 已移除；运维排障查看 App Health、worker lag、outbox、RabbitMQ、matching diagnostics 和 direct payload query profile。
- `/health` / `/health/ready` 输出 bounded `api_performance` 进程内 rolling window 摘要，按 `METHOD path` 聚合 `duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_duration_ms` 和 `database_query_count` 的 p50/p95/p99，但只保留 p95 最慢的有限 endpoint，并通过 `endpoint_count` / `omitted_endpoint_count` 标明是否被截断。完整 endpoint 明细由 `/metrics` 或 admin-only `/api/operations/app-health-dashboard` 提供。
- P2/P3 readiness payload gate 使用 `health_ready_payload_probe` 验证 `/fin-ops-api/health/ready` 本身不成为慢探针：默认要求 1000ms 内、JSON、response 不超过 50KB、`api_performance.endpoints<=20` 且带 `endpoint_count` / `omitted_endpoint_count`；ready payload 只保留 runtime blocker 需要的 counts、status summary 和 bounded problem samples，不输出完整 `entrypoints`、`worker_metrics` 或重复的 `storage.runtime_infrastructure`；慢、大、未截断、缺 metadata 或 HTML fallback 均视为失败。
- 不输出 token、密码、完整附件正文或敏感原始文件内容。
- 高风险动作需要审计日志，不只依赖应用日志。

## Runtime Queue 指标

`/health` 的 `runtime_infrastructure` 至少包含：

- `queue_backlog`：outbox 当前 backlog/attention status 聚合，不包含历史 `done`。
- `oldest_pending_event_age_seconds`：最老 pending event age。
- `worker_heartbeat_lag_seconds`：runtime worker heartbeat lag。
- `worker_metrics`：按中心 registry 展示 required worker 的 heartbeat。没有 heartbeat 的 required worker 显示 `status=missing` / `warning_code=required_worker_missing`；超过该 worker SLO 的显示 `status=stale` / `warning_code=worker_heartbeat_stale`。
- `missing_required_worker_count` / `stale_required_worker_count`：required worker 缺失或 stale 的数量。
- `redis_hit_count` / `redis_miss_count`：进程内 Redis helper 计数。

RabbitMQ 接入后仍以 PostgreSQL outbox 指标为准；RabbitMQ queue depth 和 DLQ 只能补充投递层健康度，不能代替 outbox 的事实状态。RabbitMQ 相关指标包括：

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

当关联台出现 `oa_bank_exact_sum` 把弱文本证据、OA 项目/申请人 token、已被 active relation 占用的 row，或已被 submitted no-OA batch 闭环的银行流水拼成候选时，必须先确认生成规则和 cleanup dry-run 判定已修复，再清理旧 decision；只删页面缓存或手工改一条 SQL 会被下一次 matching upsert 或 legacy projection write path 污染回来。

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
无效 decision，并写入 canonical relation/matching 事实；不要绕过 source-version guard 直接改表。
若历史上已用旧版本工具执行过 expire，导致 dry-run 已归零但页面仍展示旧 `case:decision:*` open 组，
应检查 direct Workbench payload 查询、matching diagnostics 和 relation facts，而不是补投已删除的
Workbench read-model refresh。

如果 relation facts 也发生变更，页面通过 direct API 重读当前 facts；仅清理 reconciliation decision 时，不要直接改 `app.workbench_pair_relations` 中正确的 no-OA/internal-transfer relation，也不要为了让 cleanup 命中而手工改 submitted no-OA batch。

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
- `finops_outbox_events{status=...}`、`finops_failed_jobs`。
- `finops_rabbitmq_queue_depth`、`finops_rabbitmq_dlq_count`、`finops_rabbitmq_consumer_count`、`finops_rabbitmq_publish_confirm_latency_ms{quantile=...}`。
- `finops_worker_heartbeat_lag_seconds{worker_instance=...,worker_kind=...,status=...}`、`finops_worker_required`、`finops_worker_current_effective`。
- `finops_api_duration_ms{endpoint=...,quantile=...}`、`finops_api_connection_acquire_ms{endpoint=...,quantile=...}`、`finops_api_sql_execute_fetch_ms{endpoint=...,quantile=...}`。

建议 Grafana 面板至少覆盖：

- durable outbox backlog / failed-dead-letter count、worker heartbeat lag 和 required worker missing/stale/mismatch count。
- RabbitMQ queue depth、DLQ、consumer count、publisher confirm p95。
- API endpoint p95、DB p95、connection acquire p95。
- Redis hit/miss 计数和 PostgreSQL schema/release consistency。

## AppHealth 运维状态 Dashboard

设置页 `AppHealth 运维状态` 调用：

```text
GET /api/operations/app-health-dashboard
```

它是管理员只读观测入口，不执行 retry、acknowledge、requeue、republish 或数据修复。生产排障时先看 Dashboard 定位方向，再进入对应 runbook 或后台命令处理。

Dashboard 三个区域：

- `数据`：`app.bank_transactions`、`app.invoices`、`app.oa_applications`、`app.oa_application_items` 的数量和最近同步时间。发票来源拆为普通导入、OA 解析、ETC、手工导入；其中 `OA 解析` 只代表 OCR 缓存中可判定为正式发票的去重数量，不代表附件总数、OCR 候选项总数或非正式票据数量。
- `请求`：当前 API 进程内 rolling window 的 p95/p99，包括完整请求耗时、DB 总耗时、连接获取、SQL execute/fetch 和 SQL 次数。
- `后台`：`job.outbox_events`、RabbitMQ queue/DLQ、`job.runtime_worker_heartbeats` 和 worker failure/backlog 计数。

Dashboard API 使用短 TTL 进程内缓存，默认 30 秒，可通过 `FIN_OPS_APP_HEALTH_DASHBOARD_CACHE_TTL_SECONDS` 调整。缓存过期后刷新失败时，接口返回上一份 payload，并在 `cache.warnings` 或兼容 `freshness.warnings` 中加入 `dashboard_cache_stale_after_error`；权限校验和 PostgreSQL runtime 缺失不走缓存兜底。

判读原则：

- `--` 表示 unknown 或当前无可靠样本，不等于 0。
- RabbitMQ 指标缺失时仍以 PostgreSQL outbox 和 worker heartbeat 为准。
- API/DB p95 同时升高，优先看 PostgreSQL、连接池和 top SQL。
- API p95 升高但 DB 指标不高，优先看 Python 对象构造、JSON 序列化、前端请求量和网络。
- OA 附件发票 inventory 读取 `app.oa_attachment_invoice_cache`；正式发票必须具备完整发票号码、开票日期、购销方税号、价税合计，并通过 `document_kind` / `invoice_kind` 判定为发票后再按强 identity 去重。缺少 cache 或 source bridge 时报告 unknown/告警，不回退读取 Workbench rows。
- `/health/ready` 和 `/metrics` 不再输出 read-model refresh / enqueue-to-fresh percentile；页面 SLO 以 direct API latency、runtime outbox backlog、RabbitMQ transport 和 required worker heartbeat 为准。
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

- `/health` 同源 PostgreSQL runtime summary、App Status runtime attention、outbox/worker/RabbitMQ dashboard metrics。
- PostgreSQL 连接数、`max_connections`、连接 state/application 分布。
- `read_model`、`job`、`app` 主要表体积、估算行数和大索引使用情况。
- `pg_stat_statements` top SQL；如果 extension、权限或 `shared_preload_libraries` 不满足，结果会标记 unavailable。
- 不再内置 read-model hot-path EXPLAIN probes；需要定位慢 SQL 时直接对 `pg_stat_statements` 中的具体 query 单独跑 `EXPLAIN (ANALYZE, BUFFERS)`。

该工具不采集登录态页面 API p95，因为当前 API 性能 recorder 是进程内窗口且 dashboard 接口需要认证。页面首包 p95 必须用登录态 HTTP/browser 采样另行证明，不能用只读 DB baseline 代替。

受控 synthetic read model refresh smoke 已下线。页面同步证据改由 direct API HTTP/SSE 探针、`/health/ready`
bounded payload、真实写操作 durable audit 和受控 write-operation E2E 共同证明；legacy dirty/readiness 不再作为页面读路径或闭环 gate 的 apply 入口。

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
- 页面 GET API probe 必须按 direct API payload 判定；不得要求 `read_model_status`、`cache_status` 或 `refresh_enqueued` 才算 SLO 证据。legacy 后台诊断若仍记录这些字段，只能作为删除清单或排障线索。
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
- Workbench page read-model SSE 已移除，不再作为默认 SSE smoke probe。

判定原则：

- 默认目标是首个 SSE event `<= 1000ms`；超过目标返回 `sse_first_event_slo_miss`。
- 缺少 token/cookie 返回 `auth_missing`，不能作为生产 SSE 证据。
- 返回 HTML 页面壳按 `html_response_for_api_probe` 失败；这通常表示 API prefix 或 Nginx fallback 配置错误。
- 返回非 `text/event-stream`、没有 `event:` 行或事件名不匹配均失败；失败时先区分 auth、proxy buffering、API prefix、后端 route、worker 和 readiness 源头。
- 输出不包含 token、cookie 或 Authorization header。

## 真实写操作 Outbox SLO 审计

真实写操作链路使用 durable outbox 历史审计：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --lookback-hours 24 \
  --target-ms 1000 \
  --p99-target-ms 3000 \
  --output /tmp/finops-write-operation-slo-$(date +%Y%m%d%H%M%S).json
```

默认 profile 覆盖当前高影响写操作的 durable outbox event：

- `turnover_manual_closure_or_withdraw`：`turnover_relation_changed` 必须覆盖 `turnover_ledger`、`workbench`、
  `workbench_relation`、`cost_statistics`、`search`，并匹配 `turnover_relation_zero_difference_closure`、
  `withdraw_relation` 或 `turnover_relation_withdraw` action metadata。
- `turnover_relation_extra`、`turnover_tag_selection`：必须覆盖 `turnover_ledger` scope/reason/action metadata。
- `bank_row_tags_batch`：必须覆盖银行明细、关联台和往来款相关 outbox metadata，并匹配 bank row tags action metadata。
- `bank_auto_tag_rules`、`bank_category_confirmation`、`no_oa_tag_selection`：必须能在 durable outbox 中看到对应
  scope/reason/action metadata。

判定原则：

- 工具只读 `job.outbox_events` 和 canonical 业务事实，不会发起业务写操作。
- 每个 required expectation 必须在 lookback window 内有真实样本；没有样本返回 `missing`，不能当作通过。
- 最终闭环要求 `event_sample_count > 0`、`expectation_count > 0`、`failed_expectation_count = 0` 且
  `missing_expectation_count = 0`。如果 runtime gate 返回 `write_operation_audit_empty_samples`，表示缺少真实 durable
  write 证据，应生成或审批受控写 scenario 后复跑，而不是把空样本当成性能通过。
- 新发布后的 turnover UoW 事件会把非敏感 `action_name` 写入 outbox payload；工具会用它区分共享同一 reason 的不同写操作。
- 样本必须 `event_status=done`，且 p95 enqueue-to-done `<= target-ms`、p99 enqueue-to-done `<= p99-target-ms`。
  P2/P3 一秒级闭环默认使用 p95 `1000ms`、p99 `3000ms`。
- 该工具能证明“最近真实写操作产生的 outbox event 是否及时完成”，但不能证明没有被执行过的操作；最终闭环仍需要受控
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
          "path": "/api/turnover-ledger/relations/<relation_id>/withdraw",
          "json": {
            "note": "controlled SLO smoke"
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

dry-run：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_e2e_smoke \
  --scenario /tmp/finops-write-e2e-scenarios.json \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api
```

apply：

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
export FIN_OPS_WRITE_E2E_APPROVAL_TICKET='审批单号或人工批准记录'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_e2e_smoke \
  --scenario /tmp/finops-write-e2e-scenarios.json \
  --apply \
  --approval-ticket "$FIN_OPS_WRITE_E2E_APPROVAL_TICKET" \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --write-target-ms 1000 \
  --http-target-ms 1000 \
  --output /tmp/finops-write-e2e-slo-$(date +%Y%m%d%H%M%S).json
```

执行前要求：

- scenario 必须使用可控测试对象或已确认可回滚的业务对象；不要直接对生产真实待处理业务做破坏性测试。
- `--apply` 必须带审批引用；缺少 `--approval-ticket` / `FIN_OPS_WRITE_E2E_APPROVAL_TICKET` 会返回 `status=approval_missing`，且不会连接 Postgres 或发起 mutating HTTP。
- 每个 mutating step 必须有预期状态码；工具不会把 409/403/500 继续包装成已同步。
- mutating step 如果拿到 `text/html` 或 HTML 页面壳，即使状态码匹配，也会按 `html_response_for_api_probe` 失败并跳过 write SLO claim；这通常表示 API prefix、Nginx fallback 或路径配置错误。
- 写步骤成功后，工具以数据库 `clock_timestamp()` 为起点，等待对应 operation profile 的 outbox 达到 p95
  `1000ms` / p99 `3000ms` SLO。
- post API probe 只用于验证写后页面首屏 API；最终仍要结合登录态 HTTP SLO、App Health 和审计记录。
- 输出不包含 token、cookie、Authorization header，也不输出 scenario 请求 body，只记录路径、状态码、耗时和 outbox 结果。

## 全 App 同步闭环 Gate

最终闭环使用 `runtime_sync_closure_gate` 聚合检查，避免把 direct smoke、页面 shell 或历史 audit 中任意单项误判为“全 app 已闭环”。

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
export FIN_OPS_WRITE_E2E_APPROVAL_TICKET='审批单号或人工批准记录'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --write-scenario /tmp/finops-write-e2e-scenarios.json \
  --apply-write-scenarios \
  --write-approval-ticket "$FIN_OPS_WRITE_E2E_APPROVAL_TICKET" \
  --http-target-ms 1000 \
  --sse-target-ms 1000 \
  --health-ready-target-ms 1000 \
  --write-target-ms 1000 \
  --output /tmp/finops-runtime-sync-closure-gate-$(date +%Y%m%d%H%M%S).json
```

该 gate 必须全部通过才可宣称“所有页面一秒级真同步”：

- runtime health：required worker、RabbitMQ queue/unacked/DLQ、outbox/failure rate 没有当前 blocker。
- health-ready payload：`/fin-ops-api/health/ready` 自身在 1000ms 内返回轻量 JSON，`api_performance` bounded 且带截断 metadata。
- 登录态 HTTP SLO：必须使用真实 OA token/Admin-Token/cookie，覆盖全 app 页面 shell 与首屏 API p95。
- 登录态 SSE smoke：必须使用真实 OA token/Admin-Token/cookie，覆盖 App Health 和 Workbench event-stream 首事件 `<= 1000ms`，并拒绝 HTML fallback 或错误事件名。
- 真实写操作 audit：最近真实 durable outbox 样本覆盖内置高影响 operation profile，并满足写入后 outbox done SLO。
- 受控写操作 E2E：必须提供安全、可回滚的 scenario，并显式 `--apply-write-scenarios` 和 `--write-approval-ticket` 通过 mutating HTTP + 写后 outbox + 可选 post API。

缺少真实认证、缺少 scenario、只 dry-run、缺少审批引用、invalid scenario、runtime health 缺事实字段、或 write audit 没有样本时，gate 会返回 `fail`。
Postgres-backed gates 在缺少 `FIN_OPS_POSTGRES_DATABASE_URL` / `DATABASE_URL` 时会返回
`status=configuration_missing`、`blocking_condition=database_url_required`、`required_env`、
安全 `next_actions`、`allowed_remote_evidence` 和 `forbidden_without_approval`。这表示需要在安全运行环境
配置 DB URL，或进入批准的生产只读采样分支；不能把它改成 `pass`、`skip` 或一秒级 SLO 证据。
runtime health 没有 durable queue、required worker 或 failure facts 时，`runtime_health` check
会返回 `runtime_health_missing_facts`，不能作为 worker/queue 收敛证据。
health-ready payload 慢、大、未截断、缺 `endpoint_count` / `omitted_endpoint_count` 或 HTML fallback 时，
`health_ready_payload` check 会返回 fail；这通常表示 bounded readiness fix 未部署、API prefix/Nginx fallback 错误，
或 readiness endpoint 本身已经成为慢探针。
单独的 `health_ready_payload_probe` 还会输出 `runtime_release_name`、`runtime_blocker_count` 和
`runtime_blockers`。这些字段用于在不登录服务器的第一步区分 release 未部署、outbox backlog、
failed jobs、worker mismatch、Postgres 状态异常或 runtime guard 问题。
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
- 如果没有发现候选，报告返回 `status=no_candidates`，即使传了 `--scenario-output` 也不会写空 scenario 文件；主控
  workflow 应先准备已审批、可回滚的测试对象，再重新 discovery。
- 生成的 scenario 仍需要人工确认测试对象、业务影响和回滚路径；不能直接对真实待处理业务盲目 `--apply`。

## Phase 1.5 读 API 验证

生产和 staging 的工作台列表页使用分层契约，不再把完整 group payload 当作首屏数据：

- `/api/workbench/groups?...&detail_level=summary`：列表和分页使用，响应不得包含行级 `detail_fields`、`raw_payload`、OCR 正文或附件全文。
- `/api/workbench/groups/detail?...&group_id=...`：单个 group 的完整详情，按用户动作懒加载。
- Redis page cache key 必须包含 `detail_level`，避免 summary 和 full payload 互相污染。
- 旧 Redis page cache/version key 不再是 Workbench 页面一致性证明；如果页面显示旧数据，优先查 direct payload query、进程内 recent payload cache 和前端 refetch。
- 已删除的 Workbench page-cache warmup worker 不再执行 Redis page-cache warmup；页面 GET 走 direct Workbench payload，不读该 Redis page cache。保留的 Redis version key 只用于 best-effort 失效旧兼容缓存；若页面显示旧数据，优先查 direct payload query，不再排查已删除的 warmup env。
- legacy Redis fresh-cache 只作为删除清单或后台诊断；`ReadModelQueryGateway` 已删除，页面 GET 不再通过 Redis fresh-cache 判断是否可读。
- `/api/workbench/summary` 不应在热路径全量扫描 legacy Workbench projection 来修复 counts/diagnostics；summary p95 变慢时只看 direct payload build、matching row provider 和 canonical PostgreSQL query profile。
- Workbench active generation 表属于 legacy storage/migration residue，不能再作为页面 freshness gate、readiness proof、refreshing 状态或 SLO 解释来源。
- Legacy Workbench projection 体积只作为存储迁移风险监控；如果旧表继续增长，优先排查是否有旧写入路径回归，而不是恢复 pruning worker 或页面 refresh worker。
- `/api/workbench/groups` 不带 `detail_level` 时保持 `full`，只作为兼容契约，不作为前端首屏路径。

实时加载判读：

- 页面显示“关联台正在刷新”但已有数据可见：正常，说明 direct payload 可读，后台 matching 或真实 outbox 仍在处理。
- 页面显示“关联台刷新失败”：查看 App Health、outbox failed/dead-letter、matching worker 和 worker 日志。
- 页面显示“关联台读模型不可用”：这是 legacy 文案/兼容路径残留；优先检查 direct API payload、PostgreSQL migration 和生产配置，不要回落旧全量 snapshot。
- 用户只能刷新浏览器才看到新数据：检查 direct `/api/workbench*` refetch、前端 mutation projection、App Health stream 和相关 worker/outbox 是否正常。
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

# 5. 重复采样 direct API，确认 summary 和 groups 的计数来自同一事实源且稳定。
# 旧 Workbench generation 校验脚本已删除；不要再把后台 generation 当作页面一致性证明。
for i in $(seq 1 10); do
  curl -fsS 'http://localhost:8000/api/workbench/summary?month=all' >/tmp/workbench-summary.json
  curl -fsS 'http://localhost:8000/api/workbench/groups?month=all&zone=paired&page=1&page_size=200&detail_level=summary' >/tmp/workbench-groups.json
  python3 - <<'PY'
import json
summary = json.load(open('/tmp/workbench-summary.json'))
groups = json.load(open('/tmp/workbench-groups.json'))
print({
    'summary': summary.get('summary', {}),
    'groups_total': groups.get('total'),
    'groups_row_counts': groups.get('row_counts', {}),
})
PY
  sleep 1
done
```

是否进入 Go read API sidecar 只按结果判断。第一阶段和 Phase 1.5 后同时满足以下任意 2 到 3 条，才进入 sidecar 设计：

- `/api/workbench/summary`、`/api/workbench/groups?detail_level=summary`、search/cost/tax 的核心只读 p95 仍高于 300 到 500ms。
- `connection_acquire_ms + sql_execute_fetch_ms` 低于总耗时 30% 到 40%，但整体 p95 仍高。
- Python worker/进程 CPU 持续 70% 到 90% 以上，且 direct API cache 命中后仍不下降。
- summary 物化和 groups summary 命中后仍慢，瓶颈落在对象构造、JSON 序列化、请求调度或连接并发。
- 水平扩 Python 的机器成本、内存占用或部署复杂度明显高于拆只读 sidecar。

## 收口验证报告

运行时 SQL/direct API/outbox 收敛的最终验收报告由以下命令生成：

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

生产 cutover 或最终下线旧 snapshot/Mongo/GridFS fallback 前，`--require-real-infra` 报告必须整体为 `pass`。该报告需要覆盖真实 PostgreSQL migration/queue integration、Redis TTL cache、MinIO/S3 checksum smoke、GridFS backfill/verify/orphan cleanup worker、OA Mongo source 只读探测与 `oa.sync` worker、worker `--check` 和 direct API/query 性能探测。
