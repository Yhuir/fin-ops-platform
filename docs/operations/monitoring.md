# 监控与告警

## 可逆关系写后闭环

- 生产可逆关系 smoke 统一使用 `write_operation_e2e_smoke` 的 checkpoint 模式；成功的 confirm/withdraw 从同一已提交 UoW response receipt 取得精确 `outbox_event_ids`，再按这些 IDs 查询 durable outbox/dirty scope，不得只按时间窗/profile 抽取样本。receipt ID 是因果边界；同 scope enqueue 去重到请求前已经 pending 的 durable event 时，exact-ID 查询不得再附加 `created_at` fallback 窗口，也不得用既存事件的旧 `reason/action_name` 否定本次事务 receipt。receipt 模式仍必须按 `event_type + scope_type` 完整落入登记的 operation profile，任何额外 scope/event、缺失 ID、未 done 或超时都 fail closed；无 receipt 的 fallback 模式继续严格按时间窗、reason/action 识别样本。HTTP 歧义时才回读 committed `app.workbench_idempotency_records`；证据缺失必须 fail closed。
- 受控 runner 使用 runtime 登录角色只读查询上述 durable 证据；该角色仅拥有 `SELECT`，业务写仍只能经 API/UoW 事务角色完成，runner 不得 insert/update/delete 幂等记录。
- 首次 mutation 前必须先通过固定 admin-only `GET /api/operations/app-health/page-audit?page=app-health-operations`；scenario 不能覆盖 Audit path。每个 checkpoint 再依次通过 required/optional scope 合同、worker done/dirty done、consumer API `fresh`、绑定 fixture identity 的 affected assertions、non-consumer 写前/写后 baseline equality，以及新的 18/17 页只读 System Audit。System Audit 对 `queue=backlog` / `freshness=not_fresh` 和 500/502/503/504 瞬时状态在同一受控 timeout 内轮询，权限、payload、snapshot 或 contract 错误立即失败；每次通过都必须取得未被本 scenario 使用过的新 `system_audit_id`。任一事件 ID 未被正式 profile 接受、页面/path/role 不匹配、超时未收敛或复用旧 Audit 均失败。
- 只允许 `fixture_ownership=test_owned`、最多 20 个显式 row IDs、四种登记 shape、审批票和正式 mutation contract。bank+invoice/full 只走 Workbench preview/confirm/withdraw；bank+turnover 只走 turnover closure confirm 与 canonical closure case-id withdraw；bank-flow 固定执行 submit -> withdraw -> resubmit，并以 withdraw recovery 恢复 inactive。confirm/submit 已提交而后置 gate 失败时执行声明的 recovery checkpoint；withdraw 已提交后不重复撤回；网络结果不明确时不盲重试，输出 `recovery_required`。
- 该闭环证明 App 内部已登记 canonical/read model/relation 合同，不证明外部银行/OA/发票/ETC 未漏导；外部 evidence `unknown` 可以保留，但不得扩大结论。

## 当前可观察对象

- `/health` 和 app health API。
- `GET /metrics` Prometheus text exposition。
- `GET /api/operations/app-health-dashboard` 管理员只读 Dashboard。
- `GET /api/operations/app-health/page-audit?page=input-invoice-usage` 管理员只读进项使用 canonical/relation 对账审计。
- `GET /api/operations/app-health/page-audit?page=output-invoice-collections` 管理员只读销项收款 canonical/relation 对账审计。
- `GET /api/operations/app-health/page-audit?page=<page_key>` 管理员只读页面业务 canonical/relation 对账审计；registry 全覆盖 18 页，未实现 proof 的页面 fail closed。
- OA 同步状态。
- 两个保留 read model（`workbench`、`workbench_relation`）的 dirty scopes。
- 后台任务状态。
- Runtime durable queue backlog、failed outbox event、stale read model dirty scopes。
- OA Mongo 只读同步连接错误。
- 导入和重置任务失败。

## 告警建议

生产环境至少关注：

- 后端不可用。
- OA 会话接口不可用。
- OA Mongo 只读同步连续失败或 PostgreSQL canonical commit 失败。
- 后台任务连续失败。
- `job.outbox_events` pending 积压时间持续增长。
- `job.outbox_events` failed/dead_lettered 数量非零且持续增加。
- `job.read_model_dirty_scopes` 长时间处于 pending、processing 或 failed。
- `worker_heartbeat_lag_seconds` 持续超过 worker poll interval 与任务超时阈值。
- `missing_required_worker_count > 0` 或 `stale_required_worker_count > 0`。required worker 清单来自 `runtime_worker_registry`；例如 Workbench relation worker 缺失会阻断共享 relation distribution 收敛。
- `read_model_refresh_duration_ms.p95/p99` 持续升高。
- `read_model_refresh_enqueue_to_fresh_ms.p95/p99` 持续升高。该指标从 durable outbox `created_at -> processed_at` 计算，表示真实 enqueue-to-fresh latency，不等同于单次 worker handler duration。
- `/api/workbench` 或 `/api/workbench/groups` 的 `workbench_api_metric.duration_ms` p95 超过页面 SLO。
- `/api/workbench/refresh-status` 长时间返回 `refreshing`、`stale`、`failed` 或 `unavailable`。
- `/api/workbench/refresh-status.consistency_status=failed`，或 `read_model.workbench_generation_consistency` 中存在 active inconsistent generation。该状态表示 read model 发布契约被阻断，不能靠浏览器刷新恢复。
- `/health.api_performance.endpoints[*].duration_ms.p95` 持续超过页面 SLO。
- `/health.api_performance.endpoints[*].connection_acquire_ms.p95` 持续升高，表示 PostgreSQL 连接池等待、连接建立或数据库连接资源压力。
- `/health.api_performance.endpoints[*].sql_execute_fetch_ms.p95` 持续升高，表示 SQL 执行/取数本身变慢。
- Redis `redis_miss_count` 快速增长且 PostgreSQL 热读压力同步升高。
- 数据重置任务异常结束。
- Workbench 或 `workbench_relation` 返回 `read_model_unavailable`，表示对应 SQL read repository 未配置或初始化失败；这不是允许回落旧 snapshot 的场景。Search runtime 已删除，no-OA 和其它直接读取页面的 repository 失败使用页面 canonical query 错误，不得伪装成 read-model 状态。
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
- 工作台刷新状态由 `/api/workbench/refresh-status` 有界轮询；排障同时查看 HTTP timeout、worker lag、dirty scope 和 outbox 状态。
- `/health` / `/health/ready` 输出 bounded `api_performance` 进程内 rolling window 摘要，按 `METHOD path` 聚合 `duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_duration_ms` 和 `database_query_count` 的 p50/p95/p99，但只保留 p95 最慢的有限 endpoint，并通过 `endpoint_count` / `omitted_endpoint_count` 标明是否被截断。完整 endpoint 明细由 `/metrics` 或 admin-only `/api/operations/app-health-dashboard` 提供。
- `/health` 仅是进程 liveness，HTTP 固定 200；`/health/ready` 是流量和发布门禁，`status=ready` 返回 200，`status=not_ready` 返回 503。权威原因只看响应顶层 `readiness_blockers`，probe、负载均衡和部署脚本不得再从诊断字段各自推导另一套规则。
- P2/P3 readiness payload gate 使用 `health_ready_payload_probe` 验证 `/fin-ops-api/health/ready` 本身不成为慢探针：默认要求 1000ms 内、JSON、response 不超过 50KB、`api_performance.endpoints<=20` 且带 `endpoint_count` / `omitted_endpoint_count`；ready payload 只保留 runtime blocker 需要的 counts、status summary 和 bounded problem samples，不输出完整 `entrypoints`、`worker_metrics` 或重复的 `storage.runtime_infrastructure`；慢、大、未截断、缺 metadata 或 HTML fallback 均视为失败。
- `/health/ready` 只计算当前 blocker：PostgreSQL、release/runtime guard、required worker heartbeat，以及 critical `workbench` / `workbench_relation` 的 current-effective failed/dead-letter、readiness 缺失/失败和超过 300 秒的 dirty scope。普通短暂 pending/processing、非 critical backlog 和历史已覆盖 failure 不阻断。完整历史/窗口性能指标保留在 `/health`、`/metrics` 和 admin-only Operations dashboard。
- 不输出 token、密码、完整附件正文或敏感原始文件内容。
- 高风险动作需要审计日志，不只依赖应用日志。

## 操作历史与财务事实保护

- 005 管理员通过 `/operations/history` 或 `GET /api/operations/history` 查询上线覆盖点后的 durable 逻辑操作历史；普通账号不得看到菜单或读取 API。
- 每个生产写请求至少先有 `operation.requested`。审计库不可写时业务 mutation fail closed；同一 `request_id` 的 `operation.completed` 用于核对 HTTP outcome。只有 requested 且长期没有 completed 的记录需要结合应用结构化日志排查进程中断或审计 completion 失败。
- `GET /api/operations/app-health/page-audit?page=operation-history` 必须证明 coverage marker、审计/修正/history append-only trigger 存在且启用。
- 银行流水、发票受保护字段只能经带 transaction-local actor/reason 的正式入口修正；缺少 reason 的直接 UPDATE/DELETE 会被数据库拒绝。禁止通过停用 trigger、直接改审计表或重写 relation history 处理生产问题。

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
- `read_model_refresh_slow_events`：最近 bounded 样本中最慢的有限条 outbox event 摘要，包含 event/scope/status/source_version/duration/enqueue-to-fresh/skipped 信息；该字段用于完整 runtime drilldown，不进入 `/health/ready` 热路径，也不把 `event_id` 或 `scope_key` 作为 Prometheus label。
- `read_model_refresh_current_slow_events`：`recent_6h` bounded 样本中最慢的有限条 event/scope 摘要，用于定位当前窗口内具体慢 scope；同样不作为 Prometheus label 导出。
- `stale_dirty_scope_count` 和 `stale_dirty_scopes`：超时 dirty scope 摘要。
- `redis_hit_count` / `redis_miss_count`：进程内 Redis helper 计数。

RabbitMQ 接入后仍以 PostgreSQL 指标为准；RabbitMQ queue depth 和 DLQ 只能补充投递层健康度，不能代替 outbox/dirty scope 的事实状态。`/health/ready` 不实时调用 RabbitMQ Management API，避免可选管理接口把 readiness 探针拖慢；ready payload 中出现 `rabbitmq_metric_error=ready_health_rabbitmq_metrics_skipped` 表示该探针主动跳过管理指标。完整 RabbitMQ Management 指标只在 `/health`、Prometheus 或显式启用 `FIN_OPS_APP_HEALTH_DASHBOARD_RABBITMQ_METRICS=1` 的 dashboard 路径中作为补充证据。RabbitMQ 相关指标包括：

- `rabbitmq_publish_status`：outbox 按 publish status 聚合。
- `rabbitmq_unpublished_backlog`：等待 dispatcher 投递的 pending outbox 数量。
- `rabbitmq_publish_failed_backlog`：RabbitMQ 发布失败、等待重试的 pending outbox 数量；PostgreSQL worker 已完成的事件即使保留历史 publish failure，也不属于当前 durable queue backlog。
- `rabbitmq_dispatcher_lag_seconds`：最老未发布 pending outbox age。
- `rabbitmq_publish_confirm_latency_ms`：每类 RabbitMQ dispatch event 最近 bounded 样本的 publisher confirm p50/p95/p99。
- `rabbitmq_queue_depth`：RabbitMQ workbench queue messages。
- `rabbitmq_unacked_messages`：RabbitMQ unacked delivery 数量。
- `rabbitmq_consumer_count`：RabbitMQ consumer 数量。
- `rabbitmq_dlq_count`：RabbitMQ DLQ 消息数量。
- `rabbitmq_metric_error`：RabbitMQ Management API 不可用或权限错误。

### Workbench 匹配与可见性修复

关联台不再保存或展示自动候选/decision。确定性匹配只有两种结果：满足安全规则时通过正式 relation command/UoW 写 active relation；否则不写关系，相关 canonical facts 各自保持 unpaired。出现错误配对、事实缺失或历史 metadata 影响分组时，先运行对象身份审计与统一 Workbench 页面审计，区分 canonical/relation 问题和 read-model freshness 问题；禁止恢复已删除的 candidate/decision 工具或表。

如果 active relation 本身错误，只能使用正式、带审计的 withdraw/cancel 命令处理；如果 active relation
正确而页面分组错误，应修复 projection builder 后重新部署，并通过精确 `workbench` refresh 或受控
Workbench rehydrate 发布新 active generation；页面 GET 不允许同步重算。

如果 relation facts 发生变更，只通过既有 runtime queue/backfill 入口刷新仍登记的
`workbench`、`workbench_relation` scope；银行明细、成本统计及其它 direct-canonical 页面由下一次 API
请求直接读取 canonical facts。不得直接修改 `read_model.*`，也不得为了改变页面归属而手工改正确的
no-OA/internal-transfer relation。修复后必须证明 `paired = active relation members`、
`unpaired = canonical facts - paired`、两者无交集且并集不漏事实，并等待保留 read model 的相关
dirty/outbox drained、页面 Audit 零 blocking issue。

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

- `数据`：`app.bank_transactions`、`app.invoices`、`app.oa_applications`、`app.oa_application_items` 的数量和最近同步时间。发票来源固定拆为 `手工导入`、`进项发票`、`销项发票` 和 `OA 解析`；`进项发票` / `销项发票` 按 active canonical 发票的 `invoice_type` 统计，`OA 解析` 括号内数量表示 OA 解析来源且不在手工导入中的发票数。主页面还展示最新 5 条手工银行流水和发票导入历史，右侧抽屉展示全量历史。
- `请求`：当前 API 进程内 rolling window 的 p95/p99，包括完整请求耗时、DB 总耗时、连接获取、SQL execute/fetch 和 SQL 次数。
- `后台`：`job.outbox_events`、RabbitMQ queue/DLQ、`job.runtime_worker_heartbeats`、read model refresh duration 和 dirty scope 计数。

## 进项发票使用情况全量审计

部署包含该 API 的版本后，管理员可用 Admin Token 只读触发真实库对账：

```bash
curl -sS \
  -b "Admin-Token=${FIN_OPS_HTTP_SLO_ADMIN_TOKEN}" \
  -H "Accept: application/json" \
  "https://www.yn-sourcing.com/fin-ops-api/api/operations/app-health/page-audit?page=input-invoice-usage"
```

报告 `overall_status=pass`、`audit_status.integrity=pass` 且 `audit_status.freshness=fresh`，才可作为已登记 invariant 一致的证据。`issues` 与 `*_sample_count` 是有上限样本；`issue_samples_truncated=true` 时不能把样本数当成精确问题总数。

进项使用页面已直接读取 canonical facts，旧 AppHealth refresh route 已删除。审计失败时应定位并修复对应
canonical owner 或 shared relation 事实，再复跑只读 audit；不得通过页面专属 runtime queue 绕过事实源。

## 销项发票收款情况全量审计

部署包含该 API 的版本后，管理员可用 Admin Token 只读触发真实库对账：

```bash
curl -sS \
  -b "Admin-Token=${FIN_OPS_HTTP_SLO_ADMIN_TOKEN}" \
  -H "Accept: application/json" \
  "https://www.yn-sourcing.com/fin-ops-api/api/operations/app-health/page-audit?page=output-invoice-collections"
```

报告 `overall_status=pass`、`audit_status.integrity=pass` 且 `audit_status.freshness=fresh`，才可作为已登记 invariant 一致的证据；问题计数是有上限样本。

销项收款页面已直接读取 canonical facts，旧 AppHealth refresh route 已删除。审计失败时应定位并修复对应
canonical owner 或 shared relation 事实，再复跑只读 audit；不得通过页面专属 runtime queue 绕过事实源。

## 页面业务全量审计

部署包含该 API 的版本后，管理员可用 Admin Token 只读触发已就绪页面的 App 内部对账：

```bash
curl -sS \
  -b "Admin-Token=${FIN_OPS_HTTP_SLO_ADMIN_TOKEN}" \
  -H "Accept: application/json" \
  "https://www.yn-sourcing.com/fin-ops-api/api/operations/app-health/page-audit?page=bank-details"
```

当前 18 个注册页面均为 `ready`，具体页面键以 `PAGE_AUDIT_REGISTRY` 为唯一事实源；包括本统计合同涉及的 `reconciliation-workbench`、`imports.bank-transactions`、`imports.invoices`、`imports.etc-invoices`、`cost-statistics`、`bank-details`、`oa-pending-payments`、`turnover-ledger`、`etc-tickets`、`tax-offset`、`pending-invoices`、`input-invoice-usage`、`output-invoice-collections`。若后续 registry 登记为 unavailable，接口返回 `409 page_audit_proof_unavailable`，不能作为通过证据。

报告还必须带 `proof_availability=ready`、非空 `contract_revision`、repeatable-read database snapshot，且 `audit_status.integrity=pass`、`freshness=fresh`、`queue=drained`，才可作为该页面已登记 proof 一致的证据。outbox/dirty scope 按 tenant 隔离，问题只返回样本；该审计不能证明尚未登记的 consumer projection，也不能证明外部银行/OA 系统本身没有漏同步。

Dashboard API 使用短 TTL 进程内缓存，默认 30 秒，可通过 `FIN_OPS_APP_HEALTH_DASHBOARD_CACHE_TTL_SECONDS` 调整。缓存过期后刷新失败时，接口返回上一份 payload，并在 `freshness.warnings` 中加入 `dashboard_cache_stale_after_error`；权限校验和 PostgreSQL runtime 缺失不走缓存兜底。

判读原则：

- `--` 表示 unknown 或当前无可靠样本，不等于 0。
- RabbitMQ 指标缺失时仍以 PostgreSQL outbox/dirty scopes 为准。
- API/DB p95 同时升高，优先看 PostgreSQL、连接池和 top SQL。
- API p95 升高但 DB 指标不高，优先看 Python 对象构造、JSON 序列化、前端请求量和网络。
- 发票 inventory 读取 canonical `app.invoices.source_links`：`manual_invoice_import` 计入 `手工导入`，`oa_attachment_invoice` 计入 `OA 解析`，同时带 `oa_attachment_invoice` 但不带 `manual_invoice_import` 的 active 发票计入 OA 括号数。OA 附件 OCR cache 只是解析缓存，不作为 App Health 发票 inventory 事实源；ETC 已包含在手工导入口径中，不单独展示。
- 导入历史数量只来自手工导入批次事实：流水和发票读取 `app.import_batches.success_count`。OA 解析、OA 单据同步、预览候选数、附件数和 OCR 候选项总数不得作为最近导入记录。
- Read model refresh 的“历史”指标是 bounded history：最近 7 天或每个 event type 最近 512 条完成事件，不是全库永久历史扫描。
- `/health/ready` 和 `/metrics` 的 read model refresh / enqueue-to-fresh / RabbitMQ publish confirm percentile 使用每个 event type 最近 512 条样本，不扫全历史 `done` outbox。
- `read_model_refresh_current_windows` 仍基于每个 event type 最近 512 条 bounded 样本，但按 `created_at` 过滤固定窗口；它用于当前 SLO 判定，历史滞留事件仍由 all-time bounded 指标和 slow events 保留。
- `/health/ready.runtime_infrastructure.read_model_refresh_slow_events` 和 `read_model_refresh_current_slow_events` 用于定位慢 scope；Prometheus 只导出聚合分位数，避免 event/scope 高基数 label。
- read model refresh 指标查询必须使用 bounded partial indexes；`outbox_events_read_model_refresh_metric_attention_idx` 覆盖 completed duration rows 与 failed/dead-lettered rows，避免 full health/dashboard 在大 outbox 表上因 `done OR failed` 样本条件退化为历史扫描。Dashboard scope evidence 需要任意状态的最近事件，必须走 `outbox_events_read_model_scope_evidence_idx (event_type, updated_at desc)`，不能复用 terminal-only metric index 后退化成逐 model 历史扫描。
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

该工具默认 dry-run，只选择两个保留 read model 中已有 fresh readiness 的 direct scope；显式加
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

生产 admin Browser smoke、authenticated HTTP SLO 和 controlled write-operation apply 依赖真实登录态、
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

Workbench 1-second visible polling 的容量门禁先提供 evidence JSON，再分别运行 normal/peak tier：

```bash
scripts/with-production-admin-token.sh \
  env PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --capacity-evidence /root/finops-evidence/workbench-capacity.json \
  --capacity-tier normal \
  --iterations 20 \
  --warmup 2 \
  --target-ms 1000 \
  --output /tmp/finops-workbench-capacity-normal.json
```

随后只把 `--capacity-tier normal` 改为 `peak` 并使用独立输出文件。access evidence schema 使用
`mode=access_evidence`、命名 `source/source_version/source_proof`、恰好 14 个完整自然日的
`window.started_at/window.completed_at`、`method=rolling_60s_unique_visible_clients` 和匿名
恰好 20,160 项的 `rolling_60s_unique_visible_clients` 数组；approved fallback schema 使用 `mode=capacity_contract`、
`source/contract_version/approved_by/c_normal/c_peak`。缺字段、窗口不完整、未指定 tier、target 超过有界
worker 上限或没有证据时均为 `not_measured`/失败，禁止继续发布。

Workbench browser-inclusive 可见性证据是显式 opt-in 的 Playwright case。fixture manifest 必须是 regular
non-symlink file，由 root 或当前本地 operator 持有、不可带 group/world 权限，并声明
`fixture_ownership=test_owned`。隔离 prod-equivalent browser/poller run 可显式登记一个可逆模板和准确的
`isolated_repeat_count=100`，重复执行至少 100 个 same-clock 样本；该报告必须标记
`evidence_environment=isolated_prod_equivalent_browser_poller`、`production_p99_claim=false`。生产 smoke
manifest 恰好一个真实 test-owned、exact-scope、可撤回样本，不能启用 repeat。示例：

```bash
FIN_OPS_E2E_WORKBENCH_VISIBILITY_SLO=1 \
FIN_OPS_E2E_WORKBENCH_VISIBILITY_SLO_MODE=isolated \
FIN_OPS_E2E_WORKBENCH_VISIBILITY_SLO_SAMPLES=100 \
FIN_OPS_E2E_WORKBENCH_SLO_FIXTURE_MANIFEST=/root/finops-evidence/workbench-visibility-fixtures.json \
npm --prefix web run e2e -- \
  e2e/bank-flow-rule-batches-flow.spec.ts \
  --project=chromium \
  --grep "commit-to-visible same-clock"
```

报告固定写入 `.planning/phases/40-performance-contract-hot-path-closure/40-workbench-visibility-p99.json`，
只保留哈希化 sample/batch/transaction/business identity/exact scope、generation、整数微秒 marks/segments 和分位数。
报告缺失、完整样本少于 100、segment sum 不等于 total、exact scope/generation/identity 不匹配、
total p99 `>3000ms` 或 recovery 未回到 inactive，均为 `NOT_MEASURED`/release blocked。生产 smoke 必须通过
`scripts/with-production-admin-token.sh` 注入 token，`samples=1`，只能补一行 reversible smoke，不可替代隔离 p99。

默认 probe 覆盖：

- `/fin-ops/` 以及主要业务页面 shell：关联台、银行明细、待找发票、进项使用、OA 待付款、销项收款、
  税金抵扣、成本统计、免 OA、批量账务、往来款、ETC、导入、设置和 App Health。只想临时采样单个页面时才显式传
  `--page-path`。
- `/api/session/me`、`/api/app-health`、`/api/operations/app-health-dashboard`。
- 工作台 summary/refresh-status/groups/settings、银行明细账户/流水/规则、待找发票 rows/filter-options/rules、进项发票使用
  rows/filter-options/rules、OA 待付款单一 rows 聚合/ETag 条件读取、销项收款 rows/filter-options/rules、税金抵扣、
  成本统计、免 OA、批量账务、往来款、ETC、导入 facts 和后台任务首屏 API。
- 工作台 groups probe 必须使用前端首屏同口径的 `detail_level=summary`；不带 `detail_level` 的 full payload 只用于兼容或调试，不作为页面首屏 SLO 证据。

判定原则：

- 默认目标是每个 probe p95 `<= 1000ms`；可用 `--target-ms` 调整单次阶段验收阈值。
- 仅保留的 Workbench/read-model API 可接受 `200` 或 `202`，并必须记录 `read_model_status`、`cache_status` 和 `refresh_enqueued`。直接 canonical API 不返回这些字段，只以 HTTP/result contract 和延迟判定。
- OA 待付款还必须单独统计条件 `304` 的 p50/p95/p99 和 `200/202/304` 比例；`304` body为空且不得执行rows/filter聚合，`202`不得携带旧rows。生产验收目标为fresh rows p95 `<=250ms`、p99 `<=500ms`，304 p95 `<=30ms`；未完成1000次样本前不得宣称达标。
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
  --concurrency 4 \
  --warmup 1 \
  --target-ms 1000 \
  --output /tmp/finops-public-page-shell-$(date +%Y%m%d%H%M%S).json
```
- 输出不包含 token、cookie 或 Authorization header；采样结果可以进入阶段报告和事故复盘。
- `--concurrency` 只控制每个 probe 的有界并发样本数；默认值 `1` 保持串行兼容。最终生产验收使用
  容量证据派生的 `N_normal=max(4,C_normal)` 与 `N_peak=max(8,C_peak)` 两个 tier，并同时检查 error count、
  压缩传输字节、active/peak requests、PostgreSQL acquire p95 与 SQL p95，不能只比较总耗时。
- 并发 worker 硬上限为 `8`。报告必须保留命名环境和证据窗，以及每个 probe 的
  `request_count/error_count/error_counts`、duration p50/p95/p99 和压缩 `response_bytes` p50/p95/p99；
  只记录错误分类，不记录响应业务 payload 或认证信息。
- `sync_slo_baseline.evidence_bands` 必须把 `current_production: measured` 与
  `target_scale: not_measured` 分开。只有数据库名包含 `test` 的隔离目标规模环境可以写入合成/benchmark
  数据；生产 gate 只允许认证、有界、只读 GET/health/dashboard/pg_stat 采样，禁止为补性能样本写业务数据。

## HTTP 运行时与轮询 Smoke

App Health 与 Workbench 使用有界 HTTP polling。生产验证必须同时采样 `/api/app-health`、`/api/workbench/refresh-status?month=all`、`/health/ready` 和登记的首屏 API；返回 HTML fallback、认证失败、错误状态、超时或零样本都不能算通过。

`/health.http_runtime` 与 `/metrics` 暴露 active/peak requests、body rejection 和 database backpressure rejection；`storage.runtime_infrastructure.postgres_pool` 暴露 pool stats。检查这些值时必须结合 Gunicorn worker/thread/backlog、pool acquire timeout/max waiting 和 Nginx upstream timeout，不能只看 SQL 时间。

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

默认 profile 保留旧事件名仅用于负向审计：所有 `OperationExpectation.forbidden=true`，当前写操作必须证明
银行明细、Turnover、Cost、Search、no-OA projection 等已退役页面 refresh event 样本为零。具体事件名只用于识别历史污染，
不表示当前 registry 或 required worker 重新接线这些 scope。当前唯一允许的 read-model 集合仍为 `workbench`、`workbench_relation`。

判定原则：

- 工具只读 `job.outbox_events` 和 `job.read_model_dirty_scopes`，不会发起业务写操作。
- 每个 required expectation 必须在 lookback window 内有真实样本；没有样本返回 `missing`，不能当作通过。
- 最终闭环要求 `event_sample_count > 0`、`expectation_count > 0`、`failed_expectation_count = 0` 且
  `missing_expectation_count = 0`。如果 runtime gate 返回 `write_operation_audit_empty_samples`，表示缺少真实 durable
  write 证据，应生成或审批受控写 scenario 后复跑，而不是把空样本当成性能通过。
- 新发布后的 turnover UoW 事件会把非敏感 `action_name` 写入 outbox payload；工具会用它区分共享同一 reason 的不同写操作。
- 样本必须 `event_status=done`，dirty scope 必须为空或 `done`，且 p95 enqueue-to-done `<= target-ms`、p99
  enqueue-to-done `<= p99-target-ms`。P2/P3 一秒级闭环默认使用 p95 `1000ms`、p99 `3000ms`。
- 该工具能证明“最近真实写操作产生的 refresh 是否及时完成”，但不能证明没有被执行过的操作。自动发布门禁不为补齐
  样本而修改生产业务数据；需要验证某个真实写入口时，使用下节显式、经审批、test-owned 的独立 E2E 工具。

## 独立受控写操作 E2E SLO Smoke（不属于自动 Release Gate）

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

标准 scenario 文件由运维维护为 root-owned `0600` 输入，只允许登记过的 `test_owned` 可逆 relation
shape，并必须包含 checkpoints、inverse/recovery 与最终 inactive 断言。runner 在每次 checkpoint
执行时生成独立 idempotency key，文件本身不保存可复用 mutation key。

`write_operation_scenario_discovery` 仍可生成只读候选报告，但其普通生产业务候选不得写入 release gate
的可执行标准文件。如果没有满足安全边界的 test-owned 对象，独立 write E2E runner 必须失败并先准备可回滚测试对象，
不得为了凑齐数量回退到旧 API 路径、宽泛 SQL 选择或真实待处理业务对象。

页面 / 模块 write scenario 与 approval ticket 矩阵：

该矩阵同时写入 `write_operation_scenario_discovery` 的 `page_write_scenario_policy` 和生成的 scenario JSON；
独立受控写 workflow 必须读取该矩阵，不再为标准 production smoke 逐次询问 scenario 或 approval ticket。若某类没有安全候选，记录为候选缺失并准备可回滚测试对象，
禁止回退旧 API、宽泛 SQL 或真实待处理业务对象。

| 页面 / 模块 | Apply policy | 标准写场景 | Approval ticket | 说明 |
| --- | --- | --- | --- | --- |
| 往来款 | `standing_apply` | `turnover_manual_closure_or_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 只选择已有 active Workbench relation 承载的手工往来闭环，并通过 `/api/workbench/actions/withdraw-link` 撤回；不走旧的 turnover relation 直连撤回路径。 |
| 关联台 / Workbench relation | `standing_apply` | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 只选择 test-owned、`manual_confirmed` active relation，要求有明确月份且成员行数 bounded；证明 canonical withdraw 成功、写后零页面 fan-out，并在关联台重新访问时收敛。 |
| 免 OA 流水批次 | `standing_apply` | `no_oa_bank_batch_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 只选择 test-owned、submitted 且有明确 scope month 的批次，要求银行流水成员 bounded；证明 no-OA canonical withdraw 与写后零页面 fan-out。 |
| 流水规则批量处理 | `access_convergence_evidence` | `bank_flow_rule_batch_submit` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 使用 test-owned 可逆批次；证明 submit 写后零页面 fan-out，并在当前页/消费页访问时收敛。 |
| 银行明细 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤证明零银行明细 refresh；随后 authenticated 页面 API 访问证明 exact-scope fresh gate、worker drain 与读取 SLO。 |
| 银行账户余额 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤证明零账户余额 refresh；随后账户余额访问证明自身 freshness 收敛。 |
| 待找发票 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤零 pending refresh；随后待找发票访问证明自身 exact scope 收敛。 |
| 进项发票使用情况 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤零 invoice usage refresh；随后页面访问证明自身收敛。 |
| 销项发票收款情况 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤零 output collection refresh；随后页面访问和 post API probe 证明收敛。 |
| 发票生命周期 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤零 lifecycle refresh；随后 lifecycle 消费 API 访问证明收敛。 |
| OA 待付款 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 不自动写真实 OA 付款状态；用 test-owned relation 场景证明零 OA refresh，并在页面访问时收敛。 |
| 税金抵扣 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤零 tax refresh；随后税金页访问证明 canonical invoice/certified facts 收敛。 |
| 成本统计 | `access_convergence_evidence` | 标准 test-owned 可逆场景 | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 写步骤零 Cost refresh；随后 Cost 访问按 Workbench dependency gate 两阶段收敛。 |
| 批量账务 | `access_convergence_evidence` | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` | 用 test-owned Workbench relation withdraw 证明写后零页面 fan-out和批量账务/关系页访问收敛，不新增独立 production apply。 |
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
  --write-target-ms 5000 \
  --refresh-target-ms 30000 \
  --http-target-ms 1000 \
  --timeout-seconds 120 \
  --output /tmp/finops-write-e2e-slo-$(date +%Y%m%d%H%M%S).json
```

说明：`write_operation_scenario_discovery --limit 1` 用来生成每类 operation 最多 1 条最小闭环 scenario；
`write_operation_e2e_smoke` 的写后 SLO 事件读取会按当前 scenario 的 operation expectation 过滤 outbox，并保持有效采样窗口下限。runner 在 mutation 成功后先并发执行 consumer 的正常页面 GET，再执行 zero-fan-out 审计，避免验证器自身阻塞访问触发。每个 consumer 的 `target_ms` 同时是单次 fresh HTTP 上限和该 consumer 首次访问到 fresh、业务断言通过的总耗时上限；后一计时包含 exact enqueue、worker、依赖和重试，不能只用最后一次快速 GET 冒充收敛通过。`operation_commit_to_visible_ms` 仅保留为端到端观察值。

bank+OA+invoice 的 Cost 证明允许一个 exact scope 用 `/rows == []` 表达受项目范围过滤后的确定空集，但 active checkpoint 仍必须在另一个 exact scope 断言 `project_name`、`project_id`、`expense_type` 或 `cost_allocations`，并绑定 test-owned fixture 身份；空集不能单独替代关系语义证明。
因此独立受控写 workflow 可以继续使用最小 scenario 输入；审计会拒绝同一写事务产生的任何普通页面 refresh，并由 post API probes 验证页面访问时收敛。

执行前要求：

- scenario 必须使用可控测试对象或已确认可回滚的业务对象；不要直接对生产真实待处理业务做破坏性测试。
- `--apply` 必须带审批引用；缺少 `--approval-ticket` / `FIN_OPS_WRITE_E2E_APPROVAL_TICKET` 会返回 `status=approval_missing`，且不会连接 Postgres 或发起 mutating HTTP。
- 每个 mutating step 必须有预期状态码；工具不会把 409/403/500 继续包装成已同步。
- mutating step 如果拿到 `text/html` 或 HTML 页面壳，即使状态码匹配，也会按 `html_response_for_api_probe` 失败并跳过 write SLO claim；这通常表示 API prefix、Nginx fallback 或路径配置错误。
- 正式 relation confirm/withdraw 同步完成权限、freshness、canonical 校验、事务关系写和幂等提交；普通写必须零页面 dirty/outbox。生产 standing correctness smoke 的 HTTP 写响应门禁固定为 `5000ms`，未显式收紧 scenario 时页面访问到 fresh 的 correctness 上限为 `30000ms`、总等待上限为 `120s`，fresh consumer HTTP 读取门禁为 `1000ms`。性能 closure 的 scenario 必须把每个相关 consumer `target_ms` 设为 `3000` 或更低；runner 会直接检查每个 consumer 首次页面访问到 fresh/业务可见的总耗时，超限即失败。最终仍汇总 access p95 `1000ms`、p99 `3000ms`，不能用 correctness 上限、mutation 后但访问前的空闲时间或最后一次快速 GET 冒充性能结果。
- 写步骤成功后，工具优先以事务 response receipt 的 exact event IDs 为因果边界，拒绝 operation profile 中任何 forbidden page refresh；随后 post API probes 触发消费页自身 fresh gate，并验证 access-time dirty/outbox/worker/fresh 证据。只有没有 receipt 的旧式只读性能审计才使用数据库 `clock_timestamp()` 时间窗。
- post API probe 只用于验证写后页面首屏 API；最终仍要结合登录态 HTTP SLO、App Health 和审计记录。
- 输出不包含 token、cookie、Authorization header，也不输出 scenario 请求 body，只记录路径、状态码、耗时和 outbox/readiness 结果。

## 全 App 同步闭环 Gate

自动发布闭环使用 `runtime_sync_closure_gate` 聚合检查，避免把 direct smoke、页面 shell 或历史 audit 中任意单项误判为“全 app 已闭环”。它不会读取业务 write scenario，也不会执行 confirm/withdraw。

```bash
export FIN_OPS_HTTP_SLO_ADMIN_TOKEN='真实管理员 Admin-Token'
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_sync_closure_gate \
  --base-url http://127.0.0.1:18001 \
  --page-base-url https://www.yn-sourcing.com \
  --api-prefix "" \
  --apply-read-model-smoke \
  --http-target-ms 1000 \
  --sse-target-ms 1000 \
  --health-ready-target-ms 1000 \
  --read-model-target-ms 1000 \
  --write-target-ms 1000 \
  --output /tmp/finops-runtime-sync-closure-gate-$(date +%Y%m%d%H%M%S).json
```

该 gate 必须全部通过才可宣称“所有页面一秒级真同步”：

- 双 origin：页面 shell 在公开站点探测，API 在当前 release 的内部服务 origin 探测；禁止让 Nginx 页面 fallback 掩盖内部 API 错误，也禁止把内部 API origin 当作页面站点。
- runtime health：required worker、RabbitMQ queue/unacked/DLQ、dirty scope、failure rate 没有当前 blocker。
- health-ready payload：`/fin-ops-api/health/ready` 自身在 1000ms 内返回轻量 JSON，`api_performance` bounded 且带截断 metadata。
- direct read model smoke：显式 `--apply-read-model-smoke` 后，每个 App Status read model 的 enqueue-to-fresh 在目标内。
- 登录态 HTTP SLO：必须使用真实 OA token/Admin-Token/cookie，覆盖全 app 页面 shell 与首屏 API p95。
- 登录态 HTTP SLO 若仅命中 `read_model_status=refreshing` / `refresh_enqueued`，会在同一 checkpoint 的有界 timeout
  内重新执行完整采样；最终样本仍必须全部 `fresh` 且满足 p95。鉴权、HTTP 状态、HTML fallback、响应错误或延迟
  超标不会重试或降级，freshness 到期仍未收敛也会失败。
- 真实写操作 audit：最近真实 durable outbox 样本覆盖内置高影响 operation profile，并满足写入后 outbox done SLO。
- 隔离 PostgreSQL 写探针：只在 `pg_temp` 临时表内执行 insert/read/delete/rollback，必须在目标内完成且不能留下 residue；不得修改 canonical facts、关系、read model、outbox 或 dirty scope。
- 页面 canonical audit：只读调用既有 admin audit API，不能执行修复。
- 采样顺序：所有 read-model、HTTP 与隔离写探针完成后再读取 runtime 严格快照。若 gate 幂等收敛了一次
  `status=done/publish_status=publishing` 终态，必须记录 reconciliation，并在同一 checkpoint 内再取得
  至少一个无残留、无再次 reconciliation 的干净采样；持续复发按 dispatcher/状态机故障失败。

缺少真实认证、runtime health 缺事实字段、隔离写探针失败、canonical audit 失败或 write audit 没有样本时，gate 会返回 `fail`。
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
HTTP SLO 没有 probe/sample 时，`authenticated_http_slo` check 会返回 `http_slo_empty_samples`。这通常表示 probe 配置、认证、API prefix 或采样输入错误，不能作为一秒级证据。
独立调用 `write_operation_e2e_smoke` 时，空 scenario list 返回 `input_error` / `scenario_empty`，不能作为 dry-run
或 apply 成功；apply 缺 approval 时必须在连接 PostgreSQL 或发送 mutating HTTP 前失败。该工具的证据不由
`runtime_sync_closure_gate` 自动消费，避免发布激活隐式修改生产业务关系。
write audit 没有真实 event/expectation 样本时，`write_operation_audit` check 会返回
`write_operation_audit_empty_samples`。
自动发布 workflow 应修复 durable evidence；独立业务 E2E workflow 才分流到 scenario 生成、输入修复、审批或
apply。上述失败是预期行为，不应改成 `pass` 或 `skip` 来绕过各自验收。

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
- discovery 会列出 `turnover_manual_closure_or_withdraw`、Workbench relation 与 no-OA 候选，但这些普通生产关系仅作为只读审核上下文，不再自动写入 executable scenario；当前只有 bank-flow submit 的独立正式 owner 可以生成可执行 scenario。
- 三组可逆 relation closure 必须由调用者显式提供 test-owned、bounded、confirm+withdraw checkpoint 场景，不能把 discovery 中的真实业务候选转换为测试写入。
- `turnover_manual_closure_or_withdraw` 只读上下文仍选择 active Workbench relation 支撑的手工往来闭环；其历史 standing operation 的正式入口仍是 `/api/workbench/actions/withdraw-link`。它与 bank+turnover test-owned closure 的 `/api/turnover-ledger/closures/confirm` → `/api/turnover-ledger/closures/withdraw` 是两条不同合同；后者必须捕获并消费 canonical closure case id，禁止恢复旧 relation-id 直连撤回路径。
- 生产标准对可生成的 bank-flow 场景使用 `--limit 1`，避免 full gate 串行执行过多生产写步骤。
- 如果没有发现候选，报告返回 `status=no_candidates`，即使传了 `--scenario-output` 也不会写空 scenario 文件；主控
  workflow 应先准备已审批、可回滚的测试对象，再重新 discovery。
- 生成的 bank-flow scenario 仍需要人工确认测试对象、业务影响和回滚路径；不能直接对真实待处理业务盲目 `--apply`。

可逆关系 runtime contract 随 backend release 发布，定义四个 shape（含 `bank_flow_rule_batch` 的 submit -> withdraw -> resubmit -> recovery）、正式 consumer API 与允许的业务数据根；`docs/dev/write-operation-impact-matrix.json` 是测试约束的文档镜像，runner 不在生产读取 `docs/`。Workbench/Turnover mutation 返回非预期 HTTP/HTML 时先视为 ambiguous，并只读查询 durable idempotency record：明确 committed 才允许按正式 recovery checkpoint 清理，明确 failed 才可判定未提交；missing/reserved/冲突保持 `recovery_required`，禁止盲重试或盲撤回。bank-flow 顶层 command 使用自身 batch/version 幂等合同且不接受伪造的外部 idempotency key；其响应歧义同样 fail closed 并要求人工按 request ID 核实，不能盲撤回。

没有可下发 PostgreSQL DSN 的生产环境通过 root-owned helper 执行同一 runner。scenario 必须位于
`/tmp/finops-write-e2e-*.json`、由 `finops-deploy` 持有、不可 group/world write 且不超过 1 MiB；helper
固定公网 API prefix 和 SLO，拒绝任意 Python/SQL/额外参数。apply 时 Admin Token 只能经 SSH stdin 输入：

```bash
ssh finops-deploy@finops-prod \
  sudo -n /usr/local/sbin/finops-deploy-control \
  write-operation-restore-point <release-name> <run-id>
```

对于明确 test-owned、幂等且 runner 自动执行 inverse/recovery 的 relation smoke，不把全库备份设为固定前置；
安全门是独立 idempotency key、exact receipt、失败 recovery、最终 inactive 状态和 System Audit。只有无法靠业务
inverse 完整恢复或审批明确要求时，才运行上述可选恢复点命令。已创建恢复点只允许用固定 root-owned helper 按
run-id + manifest/dump SHA-256 精确删除，禁止宽泛路径删除。通过场景安全门后执行 apply：

```bash
scripts/with-production-admin-token.sh bash -lc '
  printf "%s\n" "$FIN_OPS_HTTP_SLO_ADMIN_TOKEN" |
    ssh finops-deploy@finops-prod \
      sudo -n /usr/local/sbin/finops-deploy-control \
      write-operation-e2e-smoke <release-name> \
      /tmp/finops-write-e2e-<run-id>.json --apply-stdin
'
```

runner 结束后删除远端临时 scenario；禁止把 token 放入命令参数、scenario 或输出文件。

恢复 checkpoint 的 pre-mutation baseline 只证明 isolation/causal consumer 已 `fresh` 且当前值可读取，不执行 SLO 判定；否则慢但正确的 baseline 会阻止正式 inverse，留下 `recovery_required`。恢复写入后的 consumer probe 继续执行完整性能门。若一个 consumer 已发生 terminal SLO failure，runner 仍须继续驱动其它 retryable `refreshing` consumer 收敛，并在最终报告中保留原始 terminal failure。

普通写 API 响应中的 `outbox_event_ids` 是 transaction receipt。显式空列表表示该写入按零 fan-out 合同没有创建页面
refresh event；runner 必须保留该空 receipt，并用 operation profile 的 forbidden-event 时间窗验证，不得把空列表当成
字段缺失后强制依赖默认关闭的 durable Workbench idempotency。响应完全缺少 receipt 时才查询 durable record；每个
checkpoint 的 receipt 独立，confirm/withdraw/recovery 之间不得复用。

## Phase 1.5 读 API 验证

生产和 staging 的工作台列表页使用分层契约，不再把完整 group payload 当作首屏数据：

- `/api/workbench?month=...`：唯一首屏入口，在同一 active generation-set 快照内返回 summary 与 paired/unpaired 各首页；不应扫描 canonical facts 或全量 group rows 来现算诊断数据。
- `/api/workbench/groups?...&detail_level=summary`：列表和分页使用，响应不得包含行级 `detail_fields`、`raw_payload`、OCR 正文或附件全文。
- `/api/workbench/groups/detail?...&group_id=...`：单个 group 的完整详情，按用户动作懒加载。
- Redis 只缓存 fresh/stable gate 后的默认首屏 payload，cache key 必须包含 active generation-set version；搜索、筛选、后续分页和详情不进入该缓存。
- `worker-workbench` 不查询或预热 Redis page cache；generation 发布、下游 fan-out 与 dirty completion 热路径不承担页面 SQL/Redis I/O。页面仍从 fresh SQL read model 读取，只有 API query owner 在 fresh gate 后执行默认首屏 read-through cache。若首个用户承担冷启动，按顺序检查 Redis write 错误、首屏 TTL、`redis_miss_count` 和 cache key 的 generation version。
- 普通 read model 的 Redis fresh-cache 必须使用 `ReadModelQueryGateway` 的 fresh-gate envelope：`payload` 之外必须有 `fresh_gate.scope_key`、`fresh_gate.read_model_status=fresh`、`fresh_gate.schema_version` 和 `fresh_gate.source_versions`。命中时 gateway 会按当前 expected source versions 校验；旧格式或 source version 不匹配的 payload 只能 fail closed 回 SQL read model，不能被当作 fresh 返回。
- `/api/workbench` 不应在热路径查询 `app.bank_transactions` 或全量扫描 `read_model.workbench_group_rows` 来修复 counts/diagnostics；首屏 p95 变慢时先查 active month generation 与内部 `read_model.workbench_summary` 是否缺失，再查 refresh worker 发布失败原因。
- `read_model.workbench_generations` 中同一 `scope_key` 只能有一个 `status='active'`。如果存在 `building_generation_id` 但页面仍显示旧数据，这是正常刷新中；如果存在 `failed_generation_id`，页面仍读取 active generation，同时运维需要处理 `last_error`。
- `read_model.workbench_generations` 的非 active generation 应受 retention 控制。建议告警阈值：总 generation 数超过 300、`read_model.workbench_*` 总大小超过 10GB、根分区可用空间低于 20GB 或 `pg_wal` 异常增长。先检查 `finops-prune-workbench-generations.timer`、自动 retention 日志和 worker 是否持续重复发布同一 scope。
- `/api/workbench/groups` 不带 `detail_level` 时保持 `full`，只作为兼容契约，不作为前端首屏路径。

实时加载判读：

- 页面显示“关联台正在刷新”但已有数据可见：正常，说明前端正在使用最近稳定 read model。
- 页面显示“关联台刷新失败”：查看 `/api/workbench/refresh-status.last_error`、`job.read_model_dirty_scopes.status=failed` 和 worker 日志。
- 页面显示“关联台读模型不可用”：优先检查 PostgreSQL migration、read repository 初始化和生产配置，不要回落旧全量 snapshot。
- 用户只能刷新浏览器才看到新数据：检查 `/api/workbench/refresh-status` polling 是否被认证、代理 timeout 或页面 visibility 状态阻断，并核对 worker/dirty scope 是否收敛。
- OA 附件正式发票在 Workbench/税金中缺失时，先检查是否已 promotion 到 `app.invoices` 且 `raw_payload.source_links[].source_type='oa_attachment_invoice'`；再检查 `app.oa_attachment_invoice_cache_sources` 的 `attachment_identity_*` bridge 是否能把 parser cache 映射回真实附件。生产 repair 必须先 dry-run：

```bash
bridge_report="$(sudo -n /usr/local/sbin/finops-deploy-control \
  workbench-rehydrate <release-name> \
  --repair-attachment-identity-bridge --dry-run --json)"
bridge_fingerprint="$(printf '%s' "$bridge_report" | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["attachment_identity_bridge"]["candidate_fingerprint"])')"

sudo -n /usr/local/sbin/finops-deploy-control workbench-rehydrate <release-name> \
  --repair-attachment-identity-bridge --apply-repair \
  --expected-fingerprint "$bridge_fingerprint" --json

promotion_report="$(sudo -n /usr/local/sbin/finops-deploy-control \
  workbench-rehydrate <release-name> \
  --promote-oa-attachment-invoices --dry-run --json)"
promotion_fingerprint="$(printf '%s' "$promotion_report" | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["oa_attachment_invoice_promotion"]["candidate_fingerprint"])')"

sudo -n /usr/local/sbin/finops-deploy-control \
  workbench-rehydrate <release-name> \
  --promote-oa-attachment-invoices --apply-repair \
  --confirm-apply-oa-attachment-invoices \
  --expected-fingerprint "$promotion_fingerprint" --json
```

bridge 与 promotion apply 都必须使用紧邻 dry-run 输出的 exact fingerprint；候选集合变化时工具 fail closed，重新 dry-run，不得绕过门禁。promotion 只复用强身份 canonical invoice，并保留既有人工导入 provenance。

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

# 2. 分别压测 combined initial、groups summary、group detail、Workbench 关键词筛选与 cost/tax direct API。
# 记录每个 endpoint 的 p50/p95、平均响应体大小和错误率。

# 3. 读取 /health.api_performance，按 endpoint 对比：
# duration_ms、connection_acquire_ms、sql_execute_fetch_ms、database_query_count。

# 4. 对慢 SQL 单独跑 EXPLAIN (ANALYZE, BUFFERS)，再用 pg_stat_statements 看生产 top SQL。

# 5. 验证 combined initial 与 groups 固定同一 generation version，计数不随刷新漂移。
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.validate_workbench_generation_convergence \
  --base-url http://localhost:8000 \
  --month all \
  --zone paired \
  --iterations 10 \
  --delay-seconds 1
```

是否进入 Go read API sidecar 只按结果判断。第一阶段和 Phase 1.5 后同时满足以下任意 2 到 3 条，才进入 sidecar 设计：

- `/api/workbench`、`/api/workbench/groups?detail_level=summary`、Workbench 关键词筛选与 cost/tax direct API 的核心只读 p95 仍高于 300 到 500ms。
- `connection_acquire_ms + sql_execute_fetch_ms` 低于总耗时 30% 到 40%，但整体 p95 仍高。
- Python worker/进程 CPU 持续 70% 到 90% 以上，且 Redis/read model 命中后仍不下降。
- summary 物化和 groups summary 命中后仍慢，瓶颈落在对象构造、JSON 序列化、请求调度或连接并发。
- 水平扩 Python 的机器成本、内存占用或部署复杂度明显高于拆只读 sidecar。

## 收口验证

旧 `run_runtime_convergence_closure` 高权限收敛工具已删除，不能再作为生产验收入口。运行时验证改用当前分项 gate：`scripts/verify.sh runtime-check`、RabbitMQ staging preflight、deploy examples tests、worker `--check`、read model/API 性能探测和对应模块测试。
