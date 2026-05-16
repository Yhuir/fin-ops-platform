# 监控告警验证报告模板

本模板用于 P4-12 readiness gate。它只记录 staging 或受控环境的 Prometheus/Grafana 告警验证证据，不授权生产切流，不访问 OA 源数据库。

## 基本信息

| 字段 | 值 |
| --- | --- |
| change_id |  |
| env | staging |
| api_commit |  |
| worker_commit |  |
| prometheus_config_commit |  |
| grafana_dashboard_commit |  |
| operator |  |
| reviewed_by |  |
| Gate | **GO/NO_GO** |

## P0/P1 Alert Verification

每个 P0/P1 告警必须记录实际触发或低风险模拟结果。`observed state` 至少说明 firing、routed、resolved 三段是否可见。

| alert name | severity | trigger method | observed state | owner | GO/NO_GO | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| FinOpsApiHigh5xxRate | P1 |  |  |  | NO_GO |  |
| FinOpsApiP95LatencyHigh | P1 |  |  |  | NO_GO |  |
| FinOpsPostgresUnavailable | P0 |  |  |  | NO_GO |  |
| FinOpsPostgresBackupStale | P0 |  |  |  | NO_GO |  |
| FinOpsPostgresPitrDrillStale | P0 |  |  |  | NO_GO |  |
| FinOpsPostgresWalArchiveLagHigh | P1 |  |  |  | NO_GO |  |
| FinOpsOutboxBacklogHigh | P1 |  |  |  | NO_GO |  |
| FinOpsWorkerFailureRateHigh | P1 |  |  |  | NO_GO |  |
| FinOpsWorkerDeadLetters | P1 |  |  |  | NO_GO |  |
| FinOpsReadModelStale | P1 |  |  |  | NO_GO |  |
| FinOpsObjectStoreErrorRateHigh | P1 |  |  |  | NO_GO |  |
| FinOpsObjectChecksumMismatch | P0 |  |  |  | NO_GO |  |
| FinOpsHostDiskFreeLow | P1 |  |  |  | NO_GO |  |
| FinOpsHostCpuSaturationHigh | P1 |  |  |  | NO_GO |  |
| FinOpsHostMemoryAvailableLow | P1 |  |  |  | NO_GO |  |

## Dashboard Verification

| panel | metric checked | observed state | GO/NO_GO |
| --- | --- | --- | --- |
| API RPS / 5xx / latency | `fin_ops_http_requests_total`, `fin_ops_http_request_duration_seconds_bucket` |  | NO_GO |
| Readiness dependency failures | `fin_ops_readiness_checks_total` |  | NO_GO |
| PostgreSQL backup/PITR/WAL | `fin_ops_postgres_backup_age_seconds`, `fin_ops_postgres_pitr_drill_age_seconds`, `fin_ops_postgres_wal_archive_lag_seconds` |  | NO_GO |
| Outbox/NATS/Worker | `fin_ops_outbox_pending_events`, `fin_ops_worker_jobs_failed_total`, `fin_ops_worker_dead_letters_total` |  | NO_GO |
| Read model | `fin_ops_read_model_staleness_seconds` |  | NO_GO |
| Object storage | `fin_ops_object_store_upload_errors_total`, `fin_ops_object_store_checksum_mismatch_total` |  | NO_GO |
| Host resources | `node_filesystem_avail_bytes`, `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes` |  | NO_GO |

## Metric gaps

任何未在 staging 实际出现、未能由 exporter 或 textfile collector 提供、或无法触发对应告警的 metric 都必须列在这里，并保持总体 Gate 为 **NO_GO**。

| metric | source | owner | blocking reason | GO/NO_GO |
| --- | --- | --- | --- | --- |
| `fin_ops_postgres_backup_age_seconds` | postgres backup exporter/textfile |  | not verified | NO_GO |
| `fin_ops_postgres_pitr_drill_age_seconds` | PITR drill evidence exporter/textfile |  | not verified | NO_GO |
| `fin_ops_outbox_pending_events` | worker/outbox exporter |  | not verified | NO_GO |
| `fin_ops_worker_jobs_failed_total` | worker exporter |  | not verified | NO_GO |
| `fin_ops_read_model_staleness_seconds` | read model exporter |  | not verified | NO_GO |
| `fin_ops_object_store_checksum_mismatch_total` | object storage exporter or migration verifier |  | not verified | NO_GO |

## Notes

- 不记录请求体、文件名、发票号、流水号、用户 ID、账号、密码、完整连接串或凭据。
- Prometheus rule 校验、Grafana import 校验和截图/链接必须指向受控 staging 证据。
- 如果任一 P0/P1 告警无法触发、无法路由给 owner、无法恢复，或存在未实现 metric gap，总体 Gate 必须为 **NO_GO**。
