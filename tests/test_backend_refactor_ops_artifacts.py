from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITORING_DIR = ROOT / "deploy" / "backend-refactor" / "monitoring"
MONITORING_REPORT_TEMPLATE = (
    ROOT
    / "docs"
    / "operations"
    / "backend-refactor"
    / "monitoring-alert-verification-report-template.md"
)
READINESS_GATE = ROOT / "scripts" / "tools" / "backend_refactor_readiness_gate.py"
POSTGRES_PITR_SCRIPT = ROOT / "scripts" / "tools" / "postgres_pitr_restore_drill.py"
POSTGRES_PITR_TEMPLATE = (
    ROOT / "docs" / "operations" / "backend-refactor" / "postgresql-pitr-restore-drill-template.md"
)


REQUIRED_ALERT_COVERAGE = {
    "api_5xx": "FinOpsApiHigh5xxRate",
    "api_latency": "FinOpsApiP95LatencyHigh",
    "postgres_connectivity": "FinOpsPostgresUnavailable",
    "postgres_backup_age": "FinOpsPostgresBackupStale",
    "postgres_pitr": "FinOpsPostgresPitrDrillStale",
    "postgres_wal_lag": "FinOpsPostgresWalArchiveLagHigh",
    "outbox_backlog": "FinOpsOutboxBacklogHigh",
    "worker_failures": "FinOpsWorkerFailureRateHigh",
    "worker_dead_letters": "FinOpsWorkerDeadLetters",
    "read_model_stale": "FinOpsReadModelStale",
    "object_store_errors": "FinOpsObjectStoreErrorRateHigh",
    "object_store_checksum": "FinOpsObjectChecksumMismatch",
    "disk": "FinOpsHostDiskFreeLow",
    "cpu": "FinOpsHostCpuSaturationHigh",
    "memory": "FinOpsHostMemoryAvailableLow",
}

REQUIRED_DASHBOARD_METRICS = (
    "fin_ops_http_requests_total",
    "fin_ops_http_request_duration_seconds_bucket",
    "fin_ops_readiness_checks_total",
    "fin_ops_postgres_backup_age_seconds",
    "fin_ops_postgres_wal_archive_lag_seconds",
    "fin_ops_outbox_pending_events",
    "fin_ops_worker_jobs_failed_total",
    "fin_ops_worker_dead_letters_total",
    "fin_ops_read_model_staleness_seconds",
    "fin_ops_object_store_upload_errors_total",
    "fin_ops_object_store_checksum_mismatch_total",
    "node_filesystem_avail_bytes",
    "node_cpu_seconds_total",
    "node_memory_MemAvailable_bytes",
)


def run_script(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / script), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def load_readiness_gate_module():
    spec = importlib.util.spec_from_file_location("backend_refactor_readiness_gate", READINESS_GATE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_postgres_pitr_module():
    spec = importlib.util.spec_from_file_location("postgres_pitr_restore_drill", POSTGRES_PITR_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_evidence(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_monitoring_artifacts_are_parseable_and_secret_free() -> None:
    dashboard = json.loads(
        (MONITORING_DIR / "grafana-dashboard-finops-overview.json").read_text(encoding="utf-8")
    )
    assert "backend refactor overview" in dashboard["title"].lower()
    assert len(dashboard["panels"]) >= 6

    monitoring_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            MONITORING_DIR / "prometheus.finops.yml",
            MONITORING_DIR / "finops-alerts.yml",
            MONITORING_DIR / "grafana-dashboard-finops-overview.json",
        )
    ).lower()
    for forbidden in ("password", "token", "secret", "private_key"):
        assert forbidden not in monitoring_text


def test_alert_rules_cover_p0_and_core_refactor_failure_modes() -> None:
    alert_rules = (MONITORING_DIR / "finops-alerts.yml").read_text(encoding="utf-8")

    for alert_name in REQUIRED_ALERT_COVERAGE.values():
        assert alert_name in alert_rules


def test_dashboard_references_required_monitoring_metric_names() -> None:
    dashboard = json.loads(
        (MONITORING_DIR / "grafana-dashboard-finops-overview.json").read_text(encoding="utf-8")
    )
    dashboard_text = json.dumps(dashboard, ensure_ascii=False)

    for metric_name in REQUIRED_DASHBOARD_METRICS:
        assert metric_name in dashboard_text


def test_monitoring_report_template_captures_p0_p1_verification_fields() -> None:
    template = MONITORING_REPORT_TEMPLATE.read_text(encoding="utf-8")

    for required_text in (
        "alert name",
        "trigger method",
        "observed state",
        "owner",
        "severity",
        "GO/NO_GO",
        "Metric gaps",
        "NO_GO",
    ):
        assert required_text in template


def test_monitoring_readiness_gate_requires_structured_p0_p1_alert_evidence(
    tmp_path: Path,
) -> None:
    gate = load_readiness_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/monitoring-alert-verification-20260517.json",
        """
{
  "status": "GO",
  "metric_gaps": [],
  "alerts": [
    {
      "alert_name": "FinOpsApiHigh5xxRate",
      "trigger_method": "staging synthetic 5xx route",
      "observed_state": "firing then resolved",
      "owner": "fin-ops-oncall",
      "severity": "P1",
      "go_no_go": "GO"
    },
    {
      "alert_name": "FinOpsPostgresBackupStale",
      "trigger_method": "staging textfile metric override",
      "observed_state": "firing then resolved",
      "owner": "fin-ops-oncall",
      "severity": "P0",
      "go_no_go": "GO"
    }
  ]
}
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[7],))

    assert report["status"] == "GO"
    assert report["checks"][0]["status"] == "passed"


def test_monitoring_readiness_gate_rejects_unimplemented_metric_gaps(
    tmp_path: Path,
) -> None:
    gate = load_readiness_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/monitoring-alert-verification-20260517.json",
        """
{
  "status": "GO",
  "metric_gaps": [
    {
      "metric": "fin_ops_postgres_backup_age_seconds",
      "owner": "platform",
      "go_no_go": "NO_GO"
    }
  ],
  "alerts": [
    {
      "alert_name": "FinOpsPostgresBackupStale",
      "trigger_method": "not run",
      "observed_state": "missing metric",
      "owner": "platform",
      "severity": "P0",
      "go_no_go": "NO_GO"
    }
  ]
}
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[7],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_rollback_route_script_defaults_to_dry_run_and_refuses_unapproved_execute() -> None:
    dry_run = run_script(
        "deploy/rollback-route.sh",
        "--change",
        "CHG-20260516",
        "--route-group",
        "workbench-read",
        "--target",
        "python",
    )

    assert dry_run.returncode == 0
    payload = json.loads(dry_run.stdout)
    assert payload == {
        "action": "rollback-route",
        "dry_run": True,
        "change_id": "CHG-20260516",
        "route_group": "workbench-read",
        "target_backend": "python",
    }

    execute = run_script(
        "deploy/rollback-route.sh",
        "--change",
        "CHG-20260516",
        "--route-group",
        "workbench-read",
        "--target",
        "python",
        "--execute",
    )

    assert execute.returncode == 78
    assert "refusing route change" in execute.stderr


def test_feature_flag_script_defaults_to_dry_run_and_uses_allowlist() -> None:
    dry_run = run_script(
        "deploy/set-feature-flag.sh",
        "--change",
        "CHG-20260516",
        "--flag",
        "backend.dual_write.enabled",
        "--value",
        "false",
    )

    assert dry_run.returncode == 0
    payload = json.loads(dry_run.stdout)
    assert payload == {
        "action": "set-feature-flag",
        "dry_run": True,
        "change_id": "CHG-20260516",
        "flag": "backend.dual_write.enabled",
        "value": "false",
    }

    invalid_flag = run_script(
        "deploy/set-feature-flag.sh",
        "--change",
        "CHG-20260516",
        "--flag",
        "backend.unreviewed.enabled",
        "--value",
        "false",
    )
    assert invalid_flag.returncode == 64
    assert "allowlist" in invalid_flag.stderr

    execute = run_script(
        "deploy/set-feature-flag.sh",
        "--change",
        "CHG-20260516",
        "--flag",
        "backend.dual_write.enabled",
        "--value",
        "false",
        "--execute",
    )
    assert execute.returncode == 78
    assert "refusing feature flag change" in execute.stderr


def test_postgres_pitr_tool_generates_no_go_without_staging_environment() -> None:
    tool = load_postgres_pitr_module()

    args = tool.parse_args(["--validate-only"])
    config = tool.build_config(
        args,
        env={
            "FIN_OPS_PG_SOURCE_CONNINFO": "sensitive-source-conninfo",
            "FIN_OPS_PG_RESTORE_CONNINFO": "sensitive-restore-conninfo",
        },
    )
    report = tool.build_report(config, now=tool.parse_timestamp("2026-05-17T09:00:00+08:00"))
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

    assert report["status"] == "NO_GO"
    assert report["go_no_go"] == "NO_GO"
    assert report["executed_real_restore_drill"] is False
    assert "FIN_OPS_PG_BACKUP_DIR" in report["blockers"]
    assert "FIN_OPS_PG_RESTORE_TARGET_TIME" in report["blockers"]
    assert "sensitive-source-conninfo" not in encoded
    assert "sensitive-restore-conninfo" not in encoded


def test_postgres_pitr_tool_writes_paired_no_go_reports(tmp_path: Path) -> None:
    tool = load_postgres_pitr_module()
    json_path = tmp_path / "postgres-pitr-drill-20260517.json"
    md_path = tmp_path / "postgres-pitr-drill-20260517.md"

    exit_code = tool.main(
        [
            "--report-only",
            "--output-json",
            str(json_path),
            "--output-markdown",
            str(md_path),
            "--generated-at",
            "2026-05-17T09:00:00+08:00",
        ],
        env={},
    )

    assert exit_code == 0
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    assert payload["status"] == "NO_GO"
    assert payload["executed_real_restore_drill"] is False
    assert payload["backup_artifacts"] == []
    assert "Gate: **NO_GO**" in markdown
    assert "FIN_OPS_PG_SOURCE_CONNINFO" in markdown


def test_postgres_pitr_gate_rejects_no_go_and_template_reports(tmp_path: Path) -> None:
    gate = load_readiness_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/postgres-pitr-drill-template.md",
        "Gate: **GO**\n",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/postgres-pitr-drill-20260517.json",
        """
{
  "status": "NO_GO",
  "go_no_go": "NO_GO",
  "summary": {"no_go": 1},
  "blockers": ["missing staging environment"]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/postgres-pitr-drill-20260517.md",
        "Gate: **NO_GO**\n",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[1],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_postgres_pitr_template_documents_required_drill_fields() -> None:
    template = POSTGRES_PITR_TEMPLATE.read_text(encoding="utf-8")

    for required_text in (
        "base backup",
        "logical backup",
        "WAL archive",
        "restore target time",
        "isolated restore instance",
        "checksum",
        "sample count checks",
        "RPO",
        "RTO",
        "GO/NO_GO",
    ):
        assert required_text in template
