#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.app_mongo_staging_importer import (
    AppMongoStagingImportBuilder,
    StagingImportExecutor,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a 06A app Mongo export and optionally import it into PostgreSQL staging.",
    )
    parser.add_argument("--export-dir", type=Path, required=True, help="Directory containing manifest.json and NDJSON files.")
    parser.add_argument(
        "--migration-run-id",
        default=None,
        help="Optional UUID used as staging.mongo_export_manifest.id and staging.mongo_import_rows.manifest_id.",
    )
    parser.add_argument("--plan-path", type=Path, default=None, help="Optional path for the staging import plan JSON.")
    parser.add_argument("--report-path", type=Path, default=None, help="Optional path for the validation report JSON.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Insert into PostgreSQL staging tables. Requires psycopg and a URL from --database-url-env.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and build the plan without connecting to PostgreSQL. This is the default unless --execute is set.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Alias for the default dry-run validation mode; useful in environments without PostgreSQL.",
    )
    parser.add_argument(
        "--database-url-env",
        default="FIN_OPS_POSTGRES_MIGRATION_URL",
        help="Environment variable containing the PostgreSQL URL. The URL is never printed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.execute and (args.dry_run or args.validate_only):
        raise RuntimeError("--execute cannot be combined with --dry-run or --validate-only.")

    plan = AppMongoStagingImportBuilder().build_plan(
        export_dir=args.export_dir,
        migration_run_id=args.migration_run_id,
    )
    if args.plan_path is not None:
        args.plan_path.parent.mkdir(parents=True, exist_ok=True)
        args.plan_path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(plan.report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    summary = {
        "status": plan.report.to_dict()["status"],
        "decision": plan.report.decision["go_no_go"],
        "executed": False,
        "migration_run_id": plan.migration_run_id,
        "manifest_id": plan.manifest_record["id"],
        "staging_row_count": len(plan.rows),
        "failed_row_count": sum(plan.report.failed_row_counts.values()),
        "blocking_findings": len([item for item in plan.report.findings if item.get("severity") == "error"]),
    }

    if plan.report.has_blocking_findings:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 2

    if args.execute:
        database_url = os.getenv(args.database_url_env)
        if not database_url:
            raise RuntimeError(f"Missing PostgreSQL URL environment variable: {args.database_url_env}")
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required only when --execute is used.") from exc
        with psycopg.connect(database_url) as connection:
            StagingImportExecutor().execute(connection, plan)
        summary["executed"] = True

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
