from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "tools" / "backend_refactor_readiness_gate.py"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("backend_refactor_readiness_gate", SCRIPT_PATH)
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

    for check_id in (
        "postgres_backup_pitr",
        "migration_dry_run",
        "file_checksum",
        "api_shadow_validation",
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
            "collection count\nsummary total=50 diff=0\nchecksum ok\n"
        ),
        "docs/operations/backend-refactor/postgres-pitr-drill-20260516.md": go_report,
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
        "docs/operations/backend-refactor/monitoring-alert-verification-20260516.md": go_report,
        "docs/operations/backend-refactor/load-test-baseline-20260516.md": go_report,
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
