# 后端重构监控配置

本目录是后端重构 readiness 的仓库内监控配置草案，不包含凭据，不直接连接生产环境。

## 文件

- `prometheus.finops.yml`：Prometheus scrape 和 rule file 入口。
- `finops-alerts.yml`：P0/P1/P2 告警规则草案，覆盖 API、PostgreSQL、备份/PITR/WAL、outbox、worker、read model、对象存储和主机资源。
- `grafana-dashboard-finops-overview.json`：Grafana overview 看板草案，只引用本仓库文档定义的 `fin_ops_` metric 和 node exporter 标准 metric。
- `docs/operations/backend-refactor/monitoring-alert-verification-report-template.md`：P0/P1 告警验证证据模板。

## 使用约束

- 生产 target 必须由部署系统或配置管理替换，不要把真实公网地址、账号、密码或凭据写入本目录。
- `/metrics` 只能允许 Prometheus 或内网受控来源访问。
- PostgreSQL、Redis、NATS、MinIO 管理端不得为了采集指标开放公网。
- 这些配置必须先在 staging 触发验证，生成执行记录后才可作为 P4-12 证据。
- 不访问 OA 源数据库；OA 只允许验证本项目只读同步任务的监控状态。

## Staging 验证步骤

1. 在 staging Prometheus 中加载 `prometheus.finops.yml` 和 `finops-alerts.yml`，运行 Prometheus 配置校验或等价 YAML/rule 校验。
2. 导入 `grafana-dashboard-finops-overview.json`，确认 dashboard 面板查询能执行，缺失 metric 必须记录为 gap。
3. 通过低风险模拟或受控 textfile metric override 触发 P0/P1 告警，确认 firing、路由、owner 接收、恢复都可观察。
4. 填写 `docs/operations/backend-refactor/monitoring-alert-verification-report-template.md` 的副本，文件名使用 `monitoring-alert-verification-YYYYMMDD.md` 或等价 JSON。
5. 如果任一关键 metric 未实现、告警未触发、未绑定 owner、或截图/链接证据缺失，报告总体保持 `NO_GO`。

## 当前 metric gaps

代码当前已暴露的 Prometheus metric 只有 Axum API 的 `fin_ops_http_requests_total`、`fin_ops_http_request_duration_seconds` 和 `fin_ops_readiness_checks_total`。Python `AppHealthService` 当前返回的是应用健康 JSON payload，不是 Prometheus exporter。

以下 readiness 关键 metric 仍需要 staging exporter、textfile collector 或 SDK 埋点提供；未提供前，监控告警验证报告必须保持 `NO_GO`：

| area | metric examples | required before GO |
| --- | --- | --- |
| PostgreSQL backup/PITR/WAL | `fin_ops_postgres_backup_age_seconds`, `fin_ops_postgres_pitr_drill_age_seconds`, `fin_ops_postgres_wal_archive_lag_seconds` | exporter 或 textfile collector 接入并完成触发验证 |
| Outbox/Worker | `fin_ops_outbox_pending_events`, `fin_ops_worker_jobs_failed_total`, `fin_ops_worker_dead_letters_total` | worker/outbox metric 接入并完成 backlog、failure、dead-letter 验证 |
| Read model | `fin_ops_read_model_staleness_seconds`, `fin_ops_read_model_dirty_scopes` | read model stale 和 dirty scope 采集接入 |
| Object storage | `fin_ops_object_store_upload_errors_total`, `fin_ops_object_store_download_errors_total`, `fin_ops_object_store_checksum_mismatch_total` | 对象存储错误和 checksum 验证指标接入 |
| Host resources | `node_filesystem_avail_bytes`, `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes` | node exporter 接入并确认 env/instance label |

## Staging 验证记录应包含

```text
change_id:
env:
prometheus_config_commit:
grafana_dashboard_commit:
alerts_loaded:
manual_triggers:
  - alert:
    expected_severity:
    observed:
    routed_to:
    recovered:
metrics_targets:
  api:
  postgres:
  redis:
  nats:
  object_store:
  worker:
known_gaps:
go_no_go:
```

## JSON 证据格式

`backend_refactor_readiness_gate.py` 也接受 `monitoring-alert-verification-YYYYMMDD.json`。最小结构如下：

```json
{
  "status": "GO",
  "metric_gaps": [],
  "alerts": [
    {
      "alert_name": "FinOpsPostgresBackupStale",
      "trigger_method": "staging textfile metric override",
      "observed_state": "firing then resolved",
      "owner": "fin-ops-oncall",
      "severity": "P0",
      "go_no_go": "GO"
    },
    {
      "alert_name": "FinOpsApiHigh5xxRate",
      "trigger_method": "staging synthetic 5xx route",
      "observed_state": "firing then resolved",
      "owner": "fin-ops-oncall",
      "severity": "P1",
      "go_no_go": "GO"
    }
  ]
}
```

`metric_gaps` 非空、任一 P0/P1 `go_no_go` 不是 `GO`、或缺少 `alert_name`、`trigger_method`、`observed_state`、`owner`、`severity` 时，readiness gate 必须判定为 `NO_GO`。
