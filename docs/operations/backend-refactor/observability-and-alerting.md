# 后端重构可观测性与告警

本文定义 Axum + PostgreSQL 后端迁移期和生产期的日志、指标、看板和告警要求。它覆盖 API、PostgreSQL、Redis、NATS、Worker、MinIO/S3、App Mongo 备份、read model、OA 同步和关键业务指标。

## 边界

- 本文只定义监控与告警要求，不执行生产操作。
- 不记录、不展示、不写入任何密码、token、私钥或完整连接串。
- PostgreSQL 生产实例不得开放公网访问；监控采集通过内网、localhost exporter 或受控跳板完成。
- OA 源数据库不属于本项目备份和迁移对象；只监控本项目只读同步任务的状态、滞后和错误，不操作 OA 源库。
- App Mongo 在迁移期作为旧系统事实源和回滚参考；迁移完成后冻结归档，不立即删除。

## 日志与追踪

生产日志使用 JSON 结构化格式，统一写入集中日志系统。每条 API 请求、后台任务、外部调用和高风险业务动作都应带 trace id。

### API 日志字段

| 字段 | 要求 |
| --- | --- |
| `timestamp` | 服务端时间，使用统一时区或 UTC。 |
| `level` | `info`、`warn`、`error`。 |
| `trace_id` | 入口生成或从请求头透传，全链路一致。 |
| `request_id` | 单次 HTTP 请求唯一标识。 |
| `user_id` | OA 识别出的用户标识；未登录请求记录为空或匿名标识。 |
| `method`、`path` | HTTP 方法和归一化路径，不记录 query 中的敏感值。 |
| `status` | HTTP 状态码。 |
| `latency_ms` | 请求耗时。 |
| `error_code` | 业务错误码或依赖错误摘要。 |

禁止输出：

- OA token、cookie、数据库密码、对象存储密钥。
- 导入文件完整内容、附件正文、OCR 原文全文。
- 完整连接串、带签名的临时下载 URL。

### 任务日志字段

| 字段 | 要求 |
| --- | --- |
| `job_id` | 后台任务 ID。 |
| `job_type` | 导入解析、OA 同步、read model 重建、文件迁移等。 |
| `attempt` | 当前重试次数。 |
| `source` | 任务来源，如 API、outbox、人工重放。 |
| `status` | started、succeeded、failed、retrying、dead_letter。 |
| `duration_ms` | 本次执行耗时。 |
| `records_in`、`records_out` | 处理规模。 |
| `error_summary` | 可排查但不含敏感原文的错误摘要。 |

## 指标命名

Prometheus 指标建议统一使用 `fin_ops_` 前缀。标签必须低基数，避免把用户 ID、文件名、发票号、流水号作为 label。

通用标签：

| 标签 | 说明 |
| --- | --- |
| `env` | `dev`、`staging`、`prod`。 |
| `service` | `api`、`worker`、`outbox`、`migration`。 |
| `route` | 归一化 HTTP route，如 `/api/workbench/:month`。 |
| `job_type` | 有限集合的任务类型。 |
| `dependency` | `postgres`、`redis`、`nats`、`minio`、`mongo`、`oa_session`。 |

## 关键指标

### API

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_http_requests_total` | counter | 按 route、method、status 统计请求数。 |
| `fin_ops_http_request_duration_seconds` | histogram | API P50/P95/P99。 |
| `fin_ops_http_in_flight_requests` | gauge | 当前处理中请求。 |
| `fin_ops_http_body_rejected_total` | counter | body limit、文件大小、类型校验拒绝次数。 |
| `fin_ops_auth_failures_total` | counter | OA session 校验失败、无权限访问。 |
| `fin_ops_idempotency_conflicts_total` | counter | 幂等键冲突和重复提交。 |

### PostgreSQL

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_postgres_up` | gauge | PostgreSQL 可用性。 |
| `fin_ops_postgres_pool_connections` | gauge | API/worker 连接池已用、空闲、最大连接数。 |
| `fin_ops_postgres_query_duration_seconds` | histogram | SQL 查询耗时，按 query class 聚合。 |
| `fin_ops_postgres_slow_queries_total` | counter | 超过慢查询阈值的查询数。 |
| `fin_ops_postgres_deadlocks_total` | counter | deadlock 次数。 |
| `fin_ops_postgres_backup_age_seconds` | gauge | 最近一次逻辑备份成功距今时间。 |
| `fin_ops_postgres_pitr_drill_age_seconds` | gauge | 最近一次 PITR 或等价时间点恢复演练成功距今时间。 |
| `fin_ops_postgres_wal_archive_lag_seconds` | gauge | WAL 归档滞后。 |
| `fin_ops_postgres_table_bytes` | gauge | 表和索引容量趋势。 |
| `fin_ops_postgres_migration_status` | gauge | migration 状态，成功为 1，失败为 0。 |

### Redis

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_redis_up` | gauge | Redis 可用性。 |
| `fin_ops_redis_commands_total` | counter | Redis 命令量。 |
| `fin_ops_redis_command_errors_total` | counter | 连接错误、超时、协议错误。 |
| `fin_ops_redis_cache_hits_total` | counter | 缓存命中。 |
| `fin_ops_redis_cache_misses_total` | counter | 缓存未命中。 |
| `fin_ops_redis_memory_used_bytes` | gauge | 内存使用量。 |
| `fin_ops_redis_evicted_keys_total` | counter | key 淘汰数量。 |

### NATS JetStream

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_nats_up` | gauge | NATS 可用性。 |
| `fin_ops_nats_publish_failures_total` | counter | 发布失败数。 |
| `fin_ops_nats_consumer_pending_messages` | gauge | consumer backlog。 |
| `fin_ops_nats_ack_delay_seconds` | histogram | 消息 ack 延迟。 |
| `fin_ops_nats_redelivered_messages_total` | counter | 重投递次数。 |
| `fin_ops_nats_dead_letter_messages_total` | counter | dead letter 数。 |

### Outbox

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_outbox_pending_events` | gauge | 待发布、待重试或卡住的 outbox 事件数，按有限 `status` 聚合。 |
| `fin_ops_outbox_publish_failures_total` | counter | outbox 发布失败次数。 |
| `fin_ops_outbox_dead_letters_total` | counter | outbox 进入 dead-letter 的事件数。 |

### Worker

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_worker_jobs_started_total` | counter | 启动任务数。 |
| `fin_ops_worker_jobs_succeeded_total` | counter | 成功任务数。 |
| `fin_ops_worker_jobs_failed_total` | counter | 失败任务数。 |
| `fin_ops_worker_jobs_retried_total` | counter | 重试任务数。 |
| `fin_ops_worker_job_duration_seconds` | histogram | 任务耗时。 |
| `fin_ops_worker_dead_letters_total` | counter | 进入 dead-letter 的任务数。 |
| `fin_ops_worker_db_write_failures_total` | counter | 写 PostgreSQL 失败数。 |

### MinIO/S3

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_object_store_up` | gauge | 对象存储可用性。 |
| `fin_ops_object_store_upload_errors_total` | counter | 上传失败。 |
| `fin_ops_object_store_download_errors_total` | counter | 下载失败。 |
| `fin_ops_object_store_checksum_mismatch_total` | counter | checksum 校验失败。 |
| `fin_ops_object_store_request_duration_seconds` | histogram | 上传、下载、head object 耗时。 |
| `fin_ops_object_store_bucket_versioning_enabled` | gauge | bucket versioning 状态，启用为 1。 |

### App Mongo 备份

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_mongo_backup_last_success_timestamp_seconds` | gauge | 最近一次 App Mongo 备份成功时间。 |
| `fin_ops_mongo_backup_age_seconds` | gauge | 备份距今时间。 |
| `fin_ops_mongo_backup_size_bytes` | gauge | 最近一次 archive 大小。 |
| `fin_ops_mongo_backup_checksum_ok` | gauge | 最近一次 checksum 校验结果。 |
| `fin_ops_mongo_restore_drill_last_success_timestamp_seconds` | gauge | 最近一次恢复演练成功时间。 |
| `fin_ops_mongo_restore_collection_diff_total` | gauge | 恢复演练 collection count 差异数量。 |

### Read Model

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_read_model_rebuild_started_total` | counter | 重建启动数。 |
| `fin_ops_read_model_rebuild_failed_total` | counter | 重建失败数。 |
| `fin_ops_read_model_rebuild_duration_seconds` | histogram | 重建耗时。 |
| `fin_ops_read_model_staleness_seconds` | gauge | 读模型落后事实表的时间。 |
| `fin_ops_read_model_dirty_scopes` | gauge | 待重建 scope 数。 |
| `fin_ops_read_model_rows` | gauge | 关键读模型行数。 |

### OA 同步

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_oa_sync_runs_total` | counter | 同步运行次数。 |
| `fin_ops_oa_sync_failures_total` | counter | 同步失败次数。 |
| `fin_ops_oa_sync_lag_seconds` | gauge | OA 同步水位滞后。 |
| `fin_ops_oa_sync_records_total` | counter | 同步记录数。 |
| `fin_ops_oa_sync_duplicate_records_total` | counter | 幂等去重记录数。 |
| `fin_ops_oa_session_check_failures_total` | counter | OA 会话接口失败数。 |

### 业务指标

| 指标 | 类型 | 说明 |
| --- | --- | --- |
| `fin_ops_unreconciled_amount` | gauge | 待核销金额。 |
| `fin_ops_unreconciled_items` | gauge | 待核销条目数。 |
| `fin_ops_exception_cases_open` | gauge | 未关闭异常单数。 |
| `fin_ops_import_failures_total` | counter | 导入失败数。 |
| `fin_ops_reconciliation_write_failures_total` | counter | 核销确认、撤回、异常处理失败数。 |
| `fin_ops_audit_events_total` | counter | 审计事件数，按 action 聚合。 |

## 告警阈值建议

阈值先按 staging 和当前生产基线校准；上线初期建议偏敏感，稳定后再降噪。

| 告警 | 建议阈值 | 严重级别 | 处理方向 |
| --- | --- | --- | --- |
| API 不可用 | `/readyz` 连续 3 分钟失败 | P0 | 回滚路由或恢复依赖。 |
| API 5xx 升高 | 5 分钟 5xx 比例 > 2% 或连续 20 次 | P1 | 查看 trace、最近发布和依赖状态。 |
| API P95 过高 | 10 分钟 P95 > 1s；健康检查 P95 > 100ms | P2 | 检查 DB、队列、慢查询和 read model 命中。 |
| OA 会话接口失败 | 5 分钟失败率 > 5% | P1 | 只影响登录鉴权时升级；已缓存页面不绕过鉴权。 |
| PostgreSQL 不可用 | `fin_ops_postgres_up=0` 持续 1 分钟 | P0 | 停止切换，必要时读路由回滚。 |
| PostgreSQL 连接池耗尽 | 已用连接 > 85% 持续 5 分钟 | P1 | 限流、查慢查询、扩容池前先查泄漏。 |
| 慢查询激增 | 5 分钟慢查询 > 20 或 P99 > 3s | P2 | EXPLAIN、索引、read model 命中检查。 |
| Deadlock | 10 分钟 deadlock > 0 | P1 | 暂停相关写流量，检查事务顺序。 |
| PostgreSQL 备份过期 | 最近成功备份 > 24 小时 | P0 | 阻断上线和高风险变更。 |
| WAL 归档滞后 | 滞后 > 15 分钟 | P1 | 检查归档目标容量和网络。 |
| Redis 不可用 | `fin_ops_redis_up=0` 持续 3 分钟 | P1 | 退化缓存和限流能力，评估切回。 |
| Redis 淘汰 | 5 分钟有 key 淘汰 | P2 | 检查内存、TTL 和缓存大小。 |
| NATS backlog | 任一关键 consumer pending > 1000 或增长 15 分钟 | P1 | 扩 worker、暂停新导入、排查消费失败。 |
| Ack 延迟 | P95 ack delay > 60s 持续 10 分钟 | P2 | 检查 worker 处理耗时和下游依赖。 |
| Dead letter | 10 分钟 dead letter > 0 | P1 | 暂停进入下一切换阶段，保存样本。 |
| Worker 连续失败 | 同一 job type 5 分钟失败率 > 5% | P1 | 暂停相关后台任务入口。 |
| MinIO/S3 错误 | 上传或下载失败率 > 1% 持续 5 分钟 | P1 | 检查对象存储、网络、凭据权限。 |
| Checksum 不一致 | 任一文件 checksum mismatch | P0 | 阻断文件迁移和切读，保留 GridFS 归档。 |
| App Mongo 备份过期 | 最近成功备份 > 24 小时，或冻结点备份缺失 | P0 | 阻断生产切换。 |
| 恢复演练过期 | 最近恢复演练 > 30 天，或迁移前未演练 | P0 | 阻断切换。 |
| Read model stale | 关键 scope stale > 10 分钟 | P1 | 暂停切读或切回旧读。 |
| Read model 重建失败 | 任一关键 scope 连续失败 3 次 | P1 | 保留 dirty scope，禁止手改缓存。 |
| OA 同步滞后 | 生产水位滞后 > 30 分钟 | P2；切换期 P1 | 已缓存页面可读，但不得忽略同步差异。 |
| 导入失败升高 | 30 分钟导入失败率 > 5% | P2 | 检查文件类型、解析 worker、对象存储。 |
| 待核销金额异常变化 | 单小时变化超过基线 3 倍且无批量导入记录 | P2 | 业务复核，检查双写和 read model。 |

## Grafana 看板草案

生产至少建立以下看板：

1. `fin-ops-api-overview`
   - API RPS、P50/P95/P99、4xx/5xx、readiness dependency failure、in-flight、body reject、鉴权失败。
2. `fin-ops-database`
   - PostgreSQL up、连接池、慢查询、deadlock、表/索引容量、backup age、PITR drill age、WAL archive lag。
3. `fin-ops-async-workers`
   - outbox backlog、NATS backlog、ack delay、redelivery、dead letters、worker 成功/失败/重试、任务耗时。
4. `fin-ops-storage-and-backup`
   - MinIO/S3 上传下载错误、checksum mismatch、bucket versioning、App Mongo 备份和恢复演练状态。
5. `fin-ops-read-model-oa-sync`
   - read model stale、dirty scopes、重建耗时和失败、OA sync lag、同步失败。
6. `fin-ops-business-health`
   - 待核销金额、待核销条目、异常单、导入失败、审计事件、双写差异数。

## 仓库落地文件

P4-10 已补充可导入的监控草案；monitoring-alerts-h2 进一步对齐 Rust/Python 当前 metrics、Prometheus rules、Grafana dashboard 和 P0/P1 验证模板，作为 staging 验证入口：

| 文件 | 用途 |
| --- | --- |
| `deploy/backend-refactor/monitoring/prometheus.finops.yml` | Prometheus scrape 起点，使用内网 target 占位，不含 secret。 |
| `deploy/backend-refactor/monitoring/finops-alerts.yml` | P0/P1/P2 告警规则草案，覆盖 API 5xx/latency、PostgreSQL connectivity、backup/PITR/WAL、outbox、Worker、read model、对象存储和主机资源。 |
| `deploy/backend-refactor/monitoring/grafana-dashboard-finops-overview.json` | Grafana overview dashboard 草案，引用当前 Rust metric、文档定义的 readiness metric 和 node exporter 标准 metric。 |
| `deploy/backend-refactor/monitoring/README.md` | staging 接入步骤、边界和 P4-12 证据要求。 |
| `docs/operations/backend-refactor/monitoring-alert-verification-report-template.md` | P0/P1 告警触发、owner、severity、GO/NO_GO 和 metric gap 记录模板。 |

这些文件不是生产已接入证明。P4-13 已提交 `docs/operations/backend-refactor/monitoring-alert-verification-20260517.{json,md}` 作为当前证据：Prometheus/Grafana 配置可解析，但 staging 未提供 P0/P1 firing/routed/resolved 观测，且 backup/PITR/WAL、outbox、worker、read model、object storage、NATS 和 host resource 指标仍缺 exporter/textfile 样本，因此 gate 维持 `NO_GO`。后续 GO 证据必须额外记录 Prometheus rule 校验、P0/P1 人工触发或低风险模拟、值班升级路径和 dashboard 截图/链接。

## 健康检查

Axum 服务至少提供：

| Endpoint | 语义 |
| --- | --- |
| `/healthz` | 进程存活，不依赖外部服务。 |
| `/readyz` | API 可接流量，检查 PostgreSQL、必要配置、migration 版本。 |
| `/metrics` | Prometheus 指标，仅内网或受控采集访问。 |

可选提供依赖细分健康状态，但不得泄露 secret、内网拓扑细节或完整错误堆栈给外部用户。

## 当前落地状态

本节记录截至 monitoring-alerts-h2 的代码和运维落地状态，避免把目标能力误判为已完成能力。

| 能力 | 当前状态 | 生产前缺口 |
| --- | --- | --- |
| Axum JSON 日志 | 已有 `tracing_subscriber` JSON formatter。 | 需要接入集中日志系统，并验证 token、cookie、签名 URL 不进入日志样本。 |
| Trace/request id | 已有 `x-request-id` 透传或自动生成，并写入请求完成日志。 | 需要在 worker、outbox publisher、NATS message header 和 audit event 中贯通同一 trace id。 |
| API metrics | Rust `/metrics` 已输出 `fin_ops_http_requests_total`、`fin_ops_http_request_duration_seconds`、`fin_ops_readiness_checks_total`。 | 需要补 body reject、auth failure、idempotency conflict、业务写失败等指标。 |
| Route label | HTTP 指标使用低基数 `route` label，UUID、数字 ID、月份应归一化。 | staging 中需要用真实 API 样本确认没有发票号、流水号、文件名等高基数字段进入 label。 |
| Python app health | `AppHealthService` 返回健康 JSON payload，其中包含 dirty scope、background job 和 alert count。 | 目前不是 Prometheus exporter；如用于告警，需通过 exporter/textfile collector 转换为低基数 metric。 |
| PostgreSQL metrics | 本文定义指标和告警。 | 需要接入 postgres exporter 或等价采集，并补 backup age、PITR drill age、WAL archive lag 数据源。 |
| Outbox/Redis/NATS/MinIO metrics | 本文定义指标和告警。 | 需要接入对应 exporter 或 SDK 埋点，不得暴露管理端公网。 |
| App Mongo 备份指标 | 本文定义备份成功时间、checksum、恢复演练指标。 | 需要由备份脚本输出 Prometheus textfile 或人工日报，再进入 Grafana。 |
| 业务指标 | 本文定义待核销金额、异常单、导入失败数等指标。 | 需要从 PostgreSQL read model 或聚合任务生成，不能在请求路径扫描全量事实表。 |

### Monitoring-alerts-h2 metric gaps

下列 metric 目前不是 Rust API 已实现 metric，也不是 Python `AppHealthService` 直接暴露的 Prometheus metric。它们必须在 staging 通过 exporter、textfile collector 或 SDK 埋点接入；未接入前，`monitoring-alert-verification-*` 报告必须保持 `NO_GO`，不得用空面板或人工口头确认替代。

| gap | required metric | GO 前要求 |
| --- | --- | --- |
| PostgreSQL backup/PITR/WAL | `fin_ops_postgres_backup_age_seconds`, `fin_ops_postgres_pitr_drill_age_seconds`, `fin_ops_postgres_wal_archive_lag_seconds` | 备份与 PITR 演练流程输出可采集 metric，并完成 P0/P1 触发验证。 |
| Outbox backlog | `fin_ops_outbox_pending_events` | outbox repository 或 worker exporter 输出待发布/重试积压。 |
| Worker failures/dead letters | `fin_ops_worker_jobs_failed_total`, `fin_ops_worker_dead_letters_total` | worker exporter 输出失败率和 dead-letter counter。 |
| Read model stale | `fin_ops_read_model_staleness_seconds`, `fin_ops_read_model_dirty_scopes` | read model 重建状态输出 stale 秒数和 dirty scope 数。 |
| Object storage errors/checksum | `fin_ops_object_store_upload_errors_total`, `fin_ops_object_store_download_errors_total`, `fin_ops_object_store_checksum_mismatch_total` | 对象存储 SDK 或迁移验证器输出错误与 checksum counter。 |
| Host resources | `node_filesystem_avail_bytes`, `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes` | node exporter 接入并确认低基数 `env`、`instance` 标签。 |

## Prometheus 采集草案

以下示例只使用内网主机名占位，不包含账号、密码或 token。生产应由部署系统注入真实 target，并通过网络策略限制 `/metrics` 访问来源。

```yaml
scrape_configs:
  - job_name: fin-ops-api
    metrics_path: /metrics
    static_configs:
      - targets:
          - fin-ops-api.internal:8080
        labels:
          env: prod
          service: api

  - job_name: fin-ops-worker
    metrics_path: /metrics
    static_configs:
      - targets:
          - fin-ops-worker.internal:9100
        labels:
          env: prod
          service: worker

  - job_name: fin-ops-postgres
    static_configs:
      - targets:
          - postgres-exporter.internal:9187
        labels:
          env: prod
          service: postgres
```

采集验收：

```bash
curl -fsS http://fin-ops-api.internal:8080/healthz
curl -fsS http://fin-ops-api.internal:8080/readyz
curl -fsS http://fin-ops-api.internal:8080/metrics | grep -E 'fin_ops_http_requests_total|fin_ops_readiness_checks_total'
```

如果 `/metrics` 需要通过 Nginx 暴露给 Prometheus，必须单独限制来源网段；不要把 `/metrics` 暴露给公网用户。

## 告警规则草案

`deploy/backend-refactor/monitoring/finops-alerts.yml` 是当前可导入版本。上线前必须把 `for` 时间、阈值和值班路由按实际基线校准。

| 覆盖面 | 告警 | severity | metric 状态 |
| --- | --- | --- | --- |
| API 5xx | `FinOpsApiHigh5xxRate` | P1 | Rust 已实现 `fin_ops_http_requests_total`。 |
| API latency | `FinOpsApiP95LatencyHigh` | P1 | Rust 已实现 `fin_ops_http_request_duration_seconds` histogram。 |
| PostgreSQL connectivity | `FinOpsPostgresUnavailable`, `FinOpsApiPostgresReadinessFailures` | P0/P1 | `up{job="fin-ops-postgres"}` 依赖 exporter；API readiness counter 已实现。 |
| PostgreSQL backup/PITR/WAL | `FinOpsPostgresBackupStale`, `FinOpsPostgresPitrDrillStale`, `FinOpsPostgresWalArchiveLagHigh` | P0/P0/P1 | 仍需 backup/PITR/WAL exporter 或 textfile collector，未接入前 `NO_GO`。 |
| Outbox backlog | `FinOpsOutboxBacklogHigh` | P1 | 仍需 outbox metric，未接入前 `NO_GO`。 |
| Worker failures/dead letters | `FinOpsWorkerFailureRateHigh`, `FinOpsWorkerDeadLetters` | P1 | 仍需 worker metric，未接入前 `NO_GO`。 |
| Read model stale | `FinOpsReadModelStale` | P1 | 仍需 read model stale metric，未接入前 `NO_GO`。 |
| Object storage errors/checksum | `FinOpsObjectStoreErrorRateHigh`, `FinOpsObjectChecksumMismatch` | P1/P0 | 仍需对象存储错误和 checksum metric，未接入前 `NO_GO`。 |
| Disk/CPU/memory | `FinOpsHostDiskFreeLow`, `FinOpsHostCpuSaturationHigh`, `FinOpsHostMemoryAvailableLow` | P1 | 依赖 node exporter 标准 metric。 |
| Metric missing | `FinOpsMonitoringCriticalMetricsMissing` | P1 | 用于暴露关键 metric 未接入状态；触发时 readiness 仍为 `NO_GO`。 |

规则约束：

- `status`、`route`、`job_type`、`dependency` 等 label 必须是有限集合。
- 告警 annotation 不写 request body、文件名、发票号、流水号、token 或完整错误堆栈。
- P0/P1 告警必须对应 `production-readiness-checklist.md` 的阻断条件或回滚触发条件。

## 压测和基线记录

压测只允许在 staging 或授权的隔离环境执行，不压测 OA 源数据库，不绕过权限，不写生产数据。每次压测至少记录：

| 字段 | 说明 |
| --- | --- |
| `env` | staging、dry-run 或隔离环境。 |
| `api_commit`、`worker_commit`、`migration_version` | 被测版本。 |
| `dataset` | 脱敏数据集或 dry-run 数据集标识。 |
| `scenario` | 单月工作台、搜索、导入预览、核销写路径、read model rebuild 等。 |
| `duration`、`rps`、`concurrency` | 压测时间、吞吐和并发。 |
| `p50/p95/p99` | 延迟分位。 |
| `error_rate` | 4xx/5xx 和业务错误率。 |
| `db_pool_peak`、`slow_queries`、`deadlocks` | PostgreSQL 压力。 |
| `nats_backlog`、`worker_retry`、`dead_letters` | 异步链路压力。 |
| `go_no_go` | 是否满足上线门禁；差异和风险必须列出。 |

P4-12 之前，压测报告缺失、P0/P1 告警未配置或 read model stale 无监控，均不得进入生产切换。

## 告警分级

| 级别 | 定义 | 例子 |
| --- | --- | --- |
| P0 | 可能导致数据丢失、无法回滚、核心系统不可用。 | PostgreSQL 不可用、备份缺失、checksum mismatch。 |
| P1 | 影响核心流程或阻断切换下一阶段。 | worker dead letter、read model stale、连接池耗尽。 |
| P2 | 需要排查和趋势治理。 | P95 变慢、OA sync 滞后、导入失败率升高。 |

所有 P0/P1 告警必须绑定值班人、升级路径、处理记录和事后复盘。切换窗口内任一 P0 未解除，禁止继续切换。
