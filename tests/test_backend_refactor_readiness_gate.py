from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "tools" / "backend_refactor_readiness_gate.py"
LOAD_TEST_SCRIPT_PATH = ROOT / "scripts" / "tools" / "backend_refactor_load_test.py"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("backend_refactor_readiness_gate", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_load_test_module():
    spec = importlib.util.spec_from_file_location("backend_refactor_load_test", LOAD_TEST_SCRIPT_PATH)
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


def test_current_repository_readiness_gate_is_no_go() -> None:
    gate = load_gate_module()

    report = gate.evaluate(ROOT)

    assert report["status"] == "NO_GO"
    checks = {item["check_id"]: item for item in report["checks"]}

    assert checks["app_mongo_backup_restore"]["status"] == "passed"
    assert checks["app_mongo_backup_restore"]["blocking_prompt"] is None

    for check_id in (
        "postgres_backup_pitr",
        "migration_dry_run",
        "file_checksum",
        "api_shadow_validation",
        "nats_worker_replay",
        "read_model_rebuild",
        "monitoring_alerts",
        "load_test",
        "cutover_window_rollback",
    ):
        assert checks[check_id]["status"] != "passed"
        assert checks[check_id]["blocking_prompt"]


def test_readiness_gate_passes_only_when_all_required_evidence_is_go(tmp_path: Path) -> None:
    gate = load_gate_module()
    go_report = "go/no-go | `GO`\n"
    migration_go_report = "go/no-go | `GO`\nblocking: `false`\n"
    api_shadow_json_go_report = """
{
  "report": "api-shadow-validation-report-20260516",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 2,
    "endpoint_ids": ["bank-details-accounts", "tax-offset-calculate"],
    "permission_failure_endpoint_ids": [],
    "endpoint_errors": []
  },
  "filters": {
    "endpoint_ids": [],
    "risks": []
  },
  "summary": {
    "total": 2,
    "go": 2,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "permission_failure_cases": 0,
    "permission_failure_required_count": 0,
    "permission_failure_missing_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO", "unexpected_diff_count": 0, "source": "PostgreSQL facts", "source_categories": ["postgres_facts"]},
    {"endpoint_id": "tax-offset-calculate", "status": "GO", "unexpected_diff_count": 0, "source": "read_model", "source_categories": ["read_model"]}
  ]
}
"""
    evidence_files = {
        "docs/operations/backend-refactor/app-mongo-backup-runbook.md": (
            "go/no-go | `GO`\ncollection count\nsummary total=50 diff=0\nchecksum ok\n"
        ),
        "docs/operations/backend-refactor/postgres-pitr-drill-20260516.md": go_report,
        "docs/operations/backend-refactor/postgres-pitr-drill-20260516.json": (
            '{"status": "GO", "summary": {"no_go": 0}}\n'
        ),
        "docs/operations/backend-refactor/migration-dry-run-report-20260516.md": migration_go_report,
        "docs/operations/backend-refactor/gridfs-minio-migration-report-20260516.md": go_report,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260516.md": (
            "# api-shadow-validation-report-20260516\n\n- Gate: **GO**\n"
        ),
        "docs/operations/backend-refactor/api-shadow-validation-report-20260516.json": (
            api_shadow_json_go_report
        ),
        "docs/operations/backend-refactor/nats-worker-validation-report-20260516.md": go_report,
        "docs/operations/backend-refactor/read-model-rebuild-validation-report-20260516.md": go_report,
        "docs/operations/backend-refactor/monitoring-alert-verification-20260516.json": """
{
  "status": "GO",
  "metric_gaps": [],
  "alerts": [
    {
      "alert_name": "api_p0_5xx",
      "trigger_method": "staging synthetic trigger",
      "observed_state": "firing then resolved",
      "owner": "platform-ops",
      "severity": "P0",
      "go_no_go": "GO"
    },
    {
      "alert_name": "worker_p1_dead_letter",
      "trigger_method": "staging synthetic trigger",
      "observed_state": "firing then resolved",
      "owner": "platform-ops",
      "severity": "P1",
      "go_no_go": "GO"
    }
  ]
}
""",
        "docs/operations/backend-refactor/load-test-baseline-20260516.md": (
            "# load-test-baseline-20260516\n\n- Gate: **GO**\n"
        ),
        "docs/operations/backend-refactor/load-test-baseline-20260516.json": """
{
  "report": "load-test-baseline-20260516",
  "status": "GO",
  "start_time": "2026-05-16T10:00:00+08:00",
  "end_time": "2026-05-16T10:15:00+08:00",
  "dataset_scale": {
    "label": "staging-medium",
    "months": ["2026-04"],
    "bank_transactions": 100000,
    "invoice_rows": 100000,
    "search_rows": 1000000
  },
  "request_count": 8000,
  "concurrency": 16,
  "latency_ms": {"p50": 40.0, "p95": 220.0, "p99": 410.0},
  "error_rate": 0.0,
  "db_pool_stats": {"available": true, "max_connections": 20, "in_use": 8},
  "nats_outbox_backlog": {"available": true, "pending": 0},
  "worker_lag_seconds": {"available": true, "max": 2.0},
  "read_model_stale_seconds": {"available": true, "max": 4.0},
  "scenarios": [
    {"id": "healthz", "path": "/healthz", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 3.0, "p95": 8.0, "p99": 12.0}, "error_rate": 0.0},
    {"id": "readyz", "path": "/readyz", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 5.0, "p95": 12.0, "p99": 18.0}, "error_rate": 0.0},
    {"id": "workbench_month_read_model", "path": "/api/workbench?month=2026-04", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 80.0, "p95": 220.0, "p99": 320.0}, "error_rate": 0.0},
    {"id": "search", "path": "/api/search?q=PROJECT", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 90.0, "p95": 260.0, "p99": 380.0}, "error_rate": 0.0},
    {"id": "task_status", "path": "/api/background-jobs/sample", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 30.0, "p95": 120.0, "p99": 180.0}, "error_rate": 0.0},
    {"id": "import_metadata", "path": "/imports/files/sample", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 35.0, "p95": 130.0, "p99": 190.0}, "error_rate": 0.0},
    {"id": "cost_read_model", "path": "/api/cost-statistics?month=2026-04", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 70.0, "p95": 210.0, "p99": 300.0}, "error_rate": 0.0},
    {"id": "tax_read_model", "path": "/api/tax-offset?month=2026-04", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 70.0, "p95": 210.0, "p99": 300.0}, "error_rate": 0.0}
  ]
}
""",
        "docs/operations/backend-refactor/rollback-drill-record-20260516.md": go_report,
    }
    for relative_path, text in evidence_files.items():
        write_evidence(tmp_path, relative_path, text)

    report = gate.evaluate(tmp_path)

    assert report["status"] == "GO"
    assert report["blocking_count"] == 0
    assert all(item["status"] == "passed" for item in report["checks"])
    assert "Decision: `GO`" in gate.render_markdown(report)


def test_app_mongo_backup_requires_restore_count_and_checksum(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/app-mongo-backup-runbook.md",
        "checksum ok\n",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[0],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_app_mongo_backup_requires_machine_readable_go_marker(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/app-mongo-backup-runbook.md",
        "collection count\nsummary total=50 diff=0\nchecksum ok\n",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[0],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_migration_dry_run_go_marker_still_fails_when_report_has_blockers(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/migration-dry-run-report-20260516.md",
        "go/no-go | `GO`\nblocking: `true`\n",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[2],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_any_evidence_go_marker_fails_when_report_has_blockers(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/gridfs-minio-migration-report-20260516.md",
        "go/no-go | `GO`\nblocking: `true`\n",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[3],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_json_and_markdown_evidence_must_agree_when_both_exist(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/postgres-pitr-drill-20260516.md",
        "go/no-go | `GO`\n",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/postgres-pitr-drill-20260516.json",
        '{"status": "NO_GO", "summary": {"no_go": 1}}\n',
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[1],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_partial_and_scoped_reports_are_ignored(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/load-test-baseline-20260516-partial.md",
        "go/no-go | `GO`\n",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/load-test-baseline-20260516-scoped.json",
        '{"status": "GO"}\n',
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[8],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "missing"


def test_api_shadow_validation_accepts_paired_generated_json_and_markdown_go_report(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
    "fixture_validation": {
    "status": "GO",
    "endpoint_count": 2,
    "endpoint_ids": ["bank-details-accounts", "tax-offset-calculate"],
    "permission_failure_endpoint_ids": [],
    "endpoint_errors": []
  },
  "filters": {
    "endpoint_ids": [],
    "risks": []
  },
  "summary": {
    "total": 2,
    "go": 2,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "permission_failure_cases": 0,
    "permission_failure_required_count": 0,
    "permission_failure_missing_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO", "unexpected_diff_count": 0, "source": "PostgreSQL facts", "source_categories": ["postgres_facts"]},
    {"endpoint_id": "tax-offset-calculate", "status": "GO", "unexpected_diff_count": 0, "source": "read_model", "source_categories": ["read_model"]}
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "GO"
    assert report["checks"][0]["status"] == "passed"


def test_api_shadow_validation_rejects_json_when_top_level_status_is_not_go(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "PENDING",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_ids": ["bank-details-accounts"],
    "permission_failure_endpoint_ids": [],
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "permission_failure_cases": 0,
    "permission_failure_required_count": 0,
    "permission_failure_missing_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "bank-details-accounts",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_json_missing_permission_failure_summary_fields(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_ids": ["bank-details-accounts"],
    "permission_failure_endpoint_ids": [],
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "bank-details-accounts",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_go_json_missing_required_permission_failure_cases(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_ids": ["bank-details-accounts"],
    "permission_failure_endpoint_ids": ["bank-details-accounts"],
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "bank-details-accounts",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_accepts_go_json_with_required_permission_failure_cases(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_ids": ["bank-details-accounts"],
    "permission_failure_endpoint_ids": ["bank-details-accounts"],
    "endpoint_errors": []
  },
  "filters": {
    "endpoint_ids": [],
    "risks": []
  },
  "summary": {
    "total": 2,
    "go": 2,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "permission_failure_cases": 1,
    "permission_failure_required_count": 1,
    "permission_failure_missing_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "bank-details-accounts",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    },
    {
      "endpoint_id": "bank-details-accounts#permission_failure",
      "case": "permission_failure",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "GO"
    assert report["checks"][0]["status"] == "passed"


def test_api_shadow_validation_rejects_go_json_with_inconsistent_permission_failure_summary(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_ids": ["bank-details-accounts"],
    "permission_failure_endpoint_ids": ["bank-details-accounts"],
    "endpoint_errors": []
  },
  "summary": {
    "total": 2,
    "go": 2,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "permission_failure_cases": 1,
    "permission_failure_required_count": 0,
    "permission_failure_missing_count": 1,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "bank-details-accounts",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    },
    {
      "endpoint_id": "bank-details-accounts#permission_failure",
      "case": "permission_failure",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_generated_json_without_matching_markdown_report(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO", "unexpected_diff_count": 0, "source": "PostgreSQL facts", "source_categories": ["postgres_facts"]}
  ]
}
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_go_json_without_endpoint_source(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO", "unexpected_diff_count": 0}
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_go_json_without_source_categories(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO", "unexpected_diff_count": 0, "source": "PostgreSQL facts"}
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_filtered_subset_go_json(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 63,
    "endpoint_errors": []
  },
  "filters": {
    "endpoint_ids": ["bank-details-accounts"],
    "risks": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "bank-details-accounts",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_go_json_missing_filters(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_ids": ["bank-details-accounts"],
    "permission_failure_endpoint_ids": [],
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "permission_failure_cases": 0,
    "permission_failure_required_count": 0,
    "permission_failure_missing_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "bank-details-accounts",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_go_json_when_primary_ids_do_not_match_fixture_ids(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_ids": ["bank-details-accounts"],
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "made-up-endpoint",
      "case": "primary",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.bank_transactions",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_go_json_when_source_categories_do_not_match_source(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {
      "endpoint_id": "file-object-metadata-access",
      "status": "GO",
      "unexpected_diff_count": 0,
      "source": "PostgreSQL app.file_objects plus object storage provider",
      "source_categories": ["postgres_facts"]
    }
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_go_json_with_disallowed_endpoint_source(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO", "unexpected_diff_count": 0, "source": "app Mongo bank_details collection"}
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_generated_markdown_without_matching_json_report(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **GO**
- Unexpected diffs: 0
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_generated_markdown_no_go_report(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 1,
    "endpoint_errors": []
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO", "unexpected_diff_count": 0, "source": "PostgreSQL facts"}
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.md",
        """
# api-shadow-validation-report-20260517

- Gate: **NO_GO**
- Unexpected diffs: 1
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_generated_json_with_empty_results(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "GO",
    "endpoint_count": 42,
    "endpoint_errors": []
  },
  "summary": {
    "total": 0,
    "go": 0,
    "no_go": 0,
    "unexpected_diff_count": 0,
    "fixture_error_count": 0
  },
  "results": []
}
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_json_without_fixture_validation(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO"}
  ]
}
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_generated_json_no_go_report(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "summary": {
    "total": 2,
    "go": 1,
    "no_go": 1
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO"},
    {"endpoint_id": "tax-offset-calculate", "status": "NO_GO"}
  ]
}
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_api_shadow_validation_rejects_json_with_failed_fixture_validation(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/api-shadow-validation-report-20260517.json",
        """
{
  "report": "api-shadow-validation-report-20260517",
  "status": "GO",
  "fixture_validation": {
    "status": "NO_GO",
    "endpoint_errors": [
      {"endpoint_id": "bank-details-accounts", "missing_fields": ["contract_cases.body"]}
    ]
  },
  "summary": {
    "total": 1,
    "go": 1,
    "no_go": 0,
    "fixture_error_count": 1
  },
  "results": [
    {"endpoint_id": "bank-details-accounts", "status": "GO"}
  ]
}
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[4],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_load_test_accepts_paired_generated_json_and_markdown_go_report(
    tmp_path: Path,
) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/load-test-baseline-20260517.json",
        """
{
  "report": "load-test-baseline-20260517",
  "status": "GO",
  "start_time": "2026-05-17T09:00:00+08:00",
  "end_time": "2026-05-17T09:20:00+08:00",
  "dataset_scale": {
    "label": "staging-medium",
    "months": ["2026-04"],
    "bank_transactions": 100000,
    "invoice_rows": 100000,
    "search_rows": 1000000
  },
  "request_count": 8000,
  "concurrency": 16,
  "latency_ms": {"p50": 40.0, "p95": 220.0, "p99": 410.0},
  "error_rate": 0.0,
  "db_pool_stats": {"available": true, "max_connections": 20, "in_use": 8},
  "nats_outbox_backlog": {"available": true, "pending": 0},
  "worker_lag_seconds": {"available": true, "max": 2.0},
  "read_model_stale_seconds": {"available": true, "max": 4.0},
  "scenarios": [
    {"id": "healthz", "path": "/healthz", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 3.0, "p95": 8.0, "p99": 12.0}, "error_rate": 0.0},
    {"id": "readyz", "path": "/readyz", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 5.0, "p95": 12.0, "p99": 18.0}, "error_rate": 0.0},
    {"id": "workbench_month_read_model", "path": "/api/workbench?month=2026-04", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 80.0, "p95": 220.0, "p99": 320.0}, "error_rate": 0.0},
    {"id": "search", "path": "/api/search?q=PROJECT", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 90.0, "p95": 260.0, "p99": 380.0}, "error_rate": 0.0},
    {"id": "task_status", "path": "/api/background-jobs/sample", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 30.0, "p95": 120.0, "p99": 180.0}, "error_rate": 0.0},
    {"id": "import_metadata", "path": "/imports/files/sample", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 35.0, "p95": 130.0, "p99": 190.0}, "error_rate": 0.0},
    {"id": "cost_read_model", "path": "/api/cost-statistics?month=2026-04", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 70.0, "p95": 210.0, "p99": 300.0}, "error_rate": 0.0},
    {"id": "tax_read_model", "path": "/api/tax-offset?month=2026-04", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 70.0, "p95": 210.0, "p99": 300.0}, "error_rate": 0.0}
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/load-test-baseline-20260517.md",
        """
# load-test-baseline-20260517

- Gate: **GO**
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[8],))

    assert report["status"] == "GO"
    assert report["checks"][0]["status"] == "passed"


def test_load_test_rejects_markdown_go_without_matching_json_report(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/load-test-baseline-20260517.md",
        """
# load-test-baseline-20260517

- Gate: **GO**
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[8],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_load_test_rejects_go_json_missing_required_scenario(tmp_path: Path) -> None:
    gate = load_gate_module()

    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/load-test-baseline-20260517.json",
        """
{
  "report": "load-test-baseline-20260517",
  "status": "GO",
  "start_time": "2026-05-17T09:00:00+08:00",
  "end_time": "2026-05-17T09:20:00+08:00",
  "dataset_scale": {"label": "staging-medium"},
  "request_count": 1000,
  "concurrency": 16,
  "latency_ms": {"p50": 40.0, "p95": 220.0, "p99": 410.0},
  "error_rate": 0.0,
  "db_pool_stats": {"available": false},
  "nats_outbox_backlog": {"available": false},
  "worker_lag_seconds": {"available": false},
  "read_model_stale_seconds": {"available": false},
  "scenarios": [
    {"id": "healthz", "path": "/healthz", "status": "GO", "request_count": 1000, "latency_ms": {"p50": 3.0, "p95": 8.0, "p99": 12.0}, "error_rate": 0.0}
  ]
}
""",
    )
    write_evidence(
        tmp_path,
        "docs/operations/backend-refactor/load-test-baseline-20260517.md",
        """
# load-test-baseline-20260517

- Gate: **GO**
""",
    )

    report = gate.evaluate(tmp_path, checks=(gate.DEFAULT_CHECKS[8],))

    assert report["status"] == "NO_GO"
    assert report["checks"][0]["status"] == "failed"


def test_load_test_tool_default_scenarios_cover_required_read_paths() -> None:
    tool = load_load_test_module()

    scenario_ids = {scenario.scenario_id for scenario in tool.DEFAULT_SCENARIOS}

    assert tool.REQUIRED_SCENARIO_IDS <= scenario_ids
    assert all("oa" not in scenario.path_template.lower() for scenario in tool.DEFAULT_SCENARIOS)


def test_load_test_tool_validation_rejects_missing_staging_url_and_token() -> None:
    tool = load_load_test_module()

    args = tool.parse_args(["--dry-run"])
    config = tool.build_config(args, env={})
    errors = tool.validate_config(config)

    assert any("FIN_OPS_STAGING_BASE_URL" in error for error in errors)
    assert any("FIN_OPS_STAGING_AUTH_TOKEN" in error for error in errors)
