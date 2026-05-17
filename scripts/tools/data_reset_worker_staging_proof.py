#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from data_reset_audit_lineage import build_lineage_report  # noqa: E402


DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "operations" / "backend-refactor"
REQUIRED_EXTERNAL_EVIDENCE = (
    "real staging worker run",
    "product/ops approval source of truth",
    "backup evidence linked to a restorable point",
    "PostgreSQL PITR or restore drill evidence",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate settings_data_reset worker staging proof. Defaults to NO_GO unless real staging, "
            "approval, backup and PITR evidence are explicitly supplied."
        )
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--task-id")
    parser.add_argument("--data-reset-request-id")
    parser.add_argument("--approval-id")
    parser.add_argument("--backup-evidence-id")
    parser.add_argument("--pitr-evidence-id")
    parser.add_argument("--staging-run-id")
    parser.add_argument("--staging-environment")
    parser.add_argument("--operator-id")
    parser.add_argument("--report-date", default="20260517")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--md-output", type=Path)
    parser.add_argument("--confirm-real-staging", action="store_true")
    parser.add_argument("--confirm-product-ops-approval", action="store_true")
    parser.add_argument("--confirm-restorable-backup", action="store_true")
    parser.add_argument("--confirm-pitr-drill", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_staging_proof_report(args)
    json_path = args.json_output or args.output_dir / f"p0-data-reset-worker-staging-proof-{args.report_date}.json"
    md_path = args.md_output or args.output_dir / f"p0-data-reset-worker-staging-proof-{args.report_date}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "json_path": str(json_path), "markdown_path": str(md_path)}, ensure_ascii=False))
    return 0 if report["status"] == "GO" else 2


def build_staging_proof_report(args: argparse.Namespace) -> dict[str, Any]:
    lineage_args = argparse.Namespace(
        database_url=args.database_url,
        data_reset_request_id=args.data_reset_request_id,
        task_id=args.task_id,
        limit=20,
        output=None,
    )
    lineage = build_lineage_report(lineage_args)
    checks = [
        _check("real_staging_worker_run", args.confirm_real_staging and bool(args.staging_run_id and args.staging_environment)),
        _check("product_ops_approval", args.confirm_product_ops_approval and bool(args.approval_id)),
        _check("restorable_backup", args.confirm_restorable_backup and bool(args.backup_evidence_id)),
        _check("postgres_pitr_restore_drill", args.confirm_pitr_drill and bool(args.pitr_evidence_id)),
        _check("lineage_join", lineage.get("status") == "GO"),
    ]
    missing = [item for item in checks if item["status"] != "GO"]
    status = "GO" if not missing else "NO_GO_EXTERNAL_EVIDENCE_REQUIRED"
    return {
        "report": f"p0-data-reset-worker-staging-proof-{args.report_date}",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "scope": "settings_data_reset worker staging proof for the queue-only data reset endpoints.",
        "operator_id": args.operator_id,
        "staging_run_id": args.staging_run_id,
        "staging_environment": args.staging_environment,
        "task_id": args.task_id,
        "data_reset_request_id": args.data_reset_request_id,
        "approval_id": args.approval_id,
        "backup_evidence_id": args.backup_evidence_id,
        "pitr_evidence_id": args.pitr_evidence_id,
        "checks": checks,
        "blocking_reasons": [item["check"] for item in missing],
        "required_external_evidence": list(REQUIRED_EXTERNAL_EVIDENCE),
        "lineage_report": lineage,
        "go_no_go_reason": (
            "All staging, approval, backup, PITR and lineage evidence is present."
            if status == "GO"
            else "Local code proof exists, but real staging/product/ops approval/backup/PITR evidence is missing or incomplete."
        ),
    }


def _check(name: str, passed: bool) -> dict[str, str]:
    return {
        "check": name,
        "status": "GO" if passed else "NO_GO",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['report']}",
        "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 状态：`{report['status']}`",
        f"- 范围：{report['scope']}",
        f"- 结论：{report['go_no_go_reason']}",
        "",
        "## 检查项",
        "",
        "| Check | Status |",
        "| --- | --- |",
    ]
    for item in report["checks"]:
        lines.append(f"| `{item['check']}` | `{item['status']}` |")
    lines.extend(
        [
            "",
            "## 仍需外部证据",
            "",
        ]
    )
    for item in report["required_external_evidence"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Lineage 摘要",
            "",
            f"- lineage status：`{report['lineage_report'].get('status')}`",
            f"- lineage rows：`{len(report['lineage_report'].get('rows') or [])}`",
            f"- lineage gaps：`{len(report['lineage_report'].get('gaps') or [])}`",
            "",
            "本报告不伪造 product/ops approval、真实 staging、backup 或 PITR。缺失外部证据时必须保持 `NO_GO_EXTERNAL_EVIDENCE_REQUIRED`。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
