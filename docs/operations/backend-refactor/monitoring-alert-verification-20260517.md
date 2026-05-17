# 监控告警验证报告 20260517

## 基本信息

| 字段 | 值 |
| --- | --- |
| change_id | p4-13-observability-alerts-go |
| env | staging |
| api_commit | 0c639382 |
| worker_commit | 0c639382 |
| prometheus_config_commit | 0c639382 |
| grafana_dashboard_commit | 0c639382 |
| operator | Codex |
| reviewed_by | pending staging operations review |
| Gate | **NO_GO** |

## 结论

Prometheus rule YAML 和 Grafana dashboard JSON 均可解析；dashboard 引用了仓库文档定义的 metric names，其中 API request、latency bucket 和 readiness counter 来自当前 Rust metrics 实现。

本次没有可用的隔离 staging firing/routed/resolved 观测证据，也没有 backup/PITR/WAL、outbox、worker、read model、object storage、NATS、host resource exporter 样本。按 P0/P1 任一未触发或 metric gap 未关闭即 NO_GO 的规则，本报告保持 **NO_GO**。

## Alert Matrix

| alert name | severity | trigger method | observed state | owner | GO/NO_GO | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| FinOpsApiUnavailable | P0 | not executed; isolated staging Prometheus target firing evidence missing | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | rule exists in `finops-alerts.yml`; staging trigger evidence missing |
| FinOpsApiHigh5xxRate | P1 | not executed; no isolated staging synthetic 5xx run provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | rule references `fin_ops_http_requests_total`; Rust metric exists |
| FinOpsApiP95LatencyHigh | P1 | not executed; no isolated staging latency simulation provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | rule references `fin_ops_http_request_duration_seconds_bucket`; Rust histogram exists |
| FinOpsApiPostgresReadinessFailures | P1 | not executed; no isolated staging readiness failure run provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | rule references `fin_ops_readiness_checks_total`; Rust metric exists |
| FinOpsPostgresUnavailable | P0 | not executed; no staging postgres exporter or controlled outage evidence provided | not observed: no firing, routed, or resolved evidence captured | database-ops-oncall | NO_GO | exporter metric not observed in current code |
| FinOpsPostgresBackupStale | P0 | not executed; no staging textfile/exporter backup-age override provided | not observed: no firing, routed, or resolved evidence captured | database-ops-oncall | NO_GO | `fin_ops_postgres_backup_age_seconds` metric gap remains |
| FinOpsPostgresPitrDrillStale | P0 | not executed; no staging PITR drill age override provided | not observed: no firing, routed, or resolved evidence captured | database-ops-oncall | NO_GO | `fin_ops_postgres_pitr_drill_age_seconds` metric gap remains |
| FinOpsPostgresWalArchiveLagHigh | P1 | not executed; no staging WAL archive lag simulation provided | not observed: no firing, routed, or resolved evidence captured | database-ops-oncall | NO_GO | `fin_ops_postgres_wal_archive_lag_seconds` metric gap remains |
| FinOpsOutboxBacklogHigh | P1 | not executed; no staging outbox backlog injection provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | `fin_ops_outbox_pending_events` metric gap remains |
| FinOpsNatsBacklogGrowing | P1 | not executed; no staging NATS consumer backlog simulation provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | NATS exporter evidence missing |
| FinOpsWorkerFailureRateHigh | P1 | not executed; no staging worker failure simulation provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | worker metric gaps remain |
| FinOpsWorkerDeadLetters | P1 | not executed; no staging worker dead-letter simulation provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | `fin_ops_worker_dead_letters_total` metric gap remains |
| FinOpsOutboxDeadLetters | P1 | not executed; no staging outbox dead-letter simulation provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | `fin_ops_outbox_dead_letters_total` metric gap remains |
| FinOpsReadModelStale | P1 | not executed; no staging read-model stale metric override provided | not observed: no firing, routed, or resolved evidence captured | finance-ops-oncall | NO_GO | `fin_ops_read_model_staleness_seconds` metric gap remains |
| FinOpsObjectStoreErrorRateHigh | P1 | not executed; no staging object-store upload/download error simulation provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | object-store error metric gaps remain |
| FinOpsObjectChecksumMismatch | P0 | not executed; no staging checksum mismatch simulation provided | not observed: no firing, routed, or resolved evidence captured | platform-ops-oncall | NO_GO | `fin_ops_object_store_checksum_mismatch_total` metric gap remains |
| FinOpsHostDiskFreeLow | P1 | not executed; no staging node-exporter disk threshold simulation provided | not observed: no firing, routed, or resolved evidence captured | infrastructure-oncall | NO_GO | node exporter staging evidence missing |
| FinOpsHostCpuSaturationHigh | P1 | not executed; no staging CPU saturation simulation provided | not observed: no firing, routed, or resolved evidence captured | infrastructure-oncall | NO_GO | node exporter staging evidence missing |
| FinOpsHostMemoryAvailableLow | P1 | not executed; no staging memory pressure simulation provided | not observed: no firing, routed, or resolved evidence captured | infrastructure-oncall | NO_GO | node exporter staging evidence missing |

## Dashboard Verification

| panel | metric checked | observed state | GO/NO_GO |
| --- | --- | --- | --- |
| API RPS / 5xx / latency | `fin_ops_http_requests_total`, `fin_ops_http_request_duration_seconds_bucket` | dashboard JSON parses and references real Rust metric names; staging panel query execution evidence missing | NO_GO |
| Readiness dependency failures | `fin_ops_readiness_checks_total` | dashboard JSON parses and references real Rust metric name; staging panel query execution evidence missing | NO_GO |
| PostgreSQL backup/PITR/WAL | `fin_ops_postgres_backup_age_seconds`, `fin_ops_postgres_pitr_drill_age_seconds`, `fin_ops_postgres_wal_archive_lag_seconds` | dashboard JSON parses; required exporter/textfile metrics not implemented or not observed in staging | NO_GO |
| Outbox/NATS/Worker | `fin_ops_outbox_pending_events`, `fin_ops_nats_consumer_pending_messages`, `fin_ops_worker_jobs_failed_total`, `fin_ops_worker_dead_letters_total` | dashboard JSON parses; worker/outbox/NATS exporter metrics not observed in staging | NO_GO |
| Read model | `fin_ops_read_model_staleness_seconds`, `fin_ops_read_model_dirty_scopes` | dashboard JSON parses; read-model exporter metrics not observed in staging | NO_GO |
| Object storage | `fin_ops_object_store_upload_errors_total`, `fin_ops_object_store_download_errors_total`, `fin_ops_object_store_checksum_mismatch_total` | dashboard JSON parses; object-storage verifier/exporter metrics not observed in staging | NO_GO |
| Host resources | `node_filesystem_avail_bytes`, `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes` | dashboard JSON parses; node-exporter staging target evidence missing | NO_GO |

## Metric Gaps

| metric | source | owner | blocking reason | GO/NO_GO |
| --- | --- | --- | --- | --- |
| `fin_ops_postgres_up` | postgres exporter or API readiness gauge | database-ops-oncall | not implemented in Rust metrics and no staging exporter sample was provided | NO_GO |
| `fin_ops_postgres_backup_age_seconds` | postgres backup exporter/textfile | database-ops-oncall | not implemented and no staging backup age sample was provided | NO_GO |
| `fin_ops_postgres_pitr_drill_age_seconds` | PITR drill evidence exporter/textfile | database-ops-oncall | not implemented and no staging PITR drill age sample was provided | NO_GO |
| `fin_ops_postgres_wal_archive_lag_seconds` | WAL archive exporter/textfile | database-ops-oncall | not implemented and no staging WAL lag sample was provided | NO_GO |
| `fin_ops_outbox_pending_events` | outbox exporter | platform-ops-oncall | not implemented and no staging backlog sample was provided | NO_GO |
| `fin_ops_outbox_dead_letters_total` | outbox exporter | platform-ops-oncall | not implemented and no staging dead-letter sample was provided | NO_GO |
| `fin_ops_nats_consumer_pending_messages` | NATS exporter | platform-ops-oncall | no staging NATS exporter sample was provided | NO_GO |
| `fin_ops_worker_jobs_started_total` | worker exporter | platform-ops-oncall | not implemented and no staging worker metric sample was provided | NO_GO |
| `fin_ops_worker_jobs_failed_total` | worker exporter | platform-ops-oncall | not implemented and no staging worker failure sample was provided | NO_GO |
| `fin_ops_worker_dead_letters_total` | worker exporter | platform-ops-oncall | not implemented and no staging dead-letter sample was provided | NO_GO |
| `fin_ops_read_model_staleness_seconds` | read model exporter | finance-ops-oncall | not implemented and no staging stale scope sample was provided | NO_GO |
| `fin_ops_read_model_dirty_scopes` | read model exporter | finance-ops-oncall | not implemented and no staging dirty scope sample was provided | NO_GO |
| `fin_ops_object_store_upload_errors_total` | object storage exporter or API storage metrics | platform-ops-oncall | not implemented and no staging upload error sample was provided | NO_GO |
| `fin_ops_object_store_download_errors_total` | object storage exporter or API storage metrics | platform-ops-oncall | not implemented and no staging download error sample was provided | NO_GO |
| `fin_ops_object_store_checksum_mismatch_total` | object storage migration verifier/exporter | platform-ops-oncall | not implemented and no staging checksum mismatch sample was provided | NO_GO |
| `node_filesystem_avail_bytes/node_filesystem_size_bytes` | node exporter | infrastructure-oncall | no staging node-exporter sample was provided | NO_GO |
| `node_cpu_seconds_total` | node exporter | infrastructure-oncall | no staging node-exporter sample was provided | NO_GO |
| `node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes` | node exporter | infrastructure-oncall | no staging node-exporter sample was provided | NO_GO |

## Verification Evidence

- `PYTHONPATH=backend/src python3 -m pytest tests/test_backend_refactor_ops_artifacts.py -q`: 12 passed.
- `python3 -m json.tool deploy/backend-refactor/monitoring/grafana-dashboard-finops-overview.json >/tmp/finops-dashboard-check.json`: passed.
- YAML parser: `finops-alerts.yml` and `prometheus.finops.yml` parsed with PyYAML.
- Current Rust metrics implementation exports only API request counters/histograms and readiness counters.
- Python `AppHealthService` emits JSON health payload fields, not Prometheus exporter metrics.

## Remaining Blockers

- No isolated staging Prometheus firing/routed/resolved evidence was provided for any P0/P1 alert.
- Only API HTTP and readiness Prometheus metrics are implemented in current Rust code.
- Backup/PITR/WAL, outbox, worker, read model, object storage, NATS and host resource metrics are not proven by staging exporter samples.
- Because metric gaps are non-empty and all P0/P1 alerts are NO_GO, readiness gate must remain NO_GO.
