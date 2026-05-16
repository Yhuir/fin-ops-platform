#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from fin_ops_platform.services.app_mongo_migration_dry_run import (
    AppMongoMigrationDryRunBuilder,
    MigrationDryRunExecutor,
)
from fin_ops_platform.services.app_mongo_staging_importer import AppMongoStagingImportBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a secret-free app Mongo staging -> PostgreSQL facts dry-run reconciliation report.",
    )
    parser.add_argument("--export-dir", type=Path, required=True, help="Directory containing 06A manifest.json and NDJSON files.")
    parser.add_argument(
        "--migration-run-id",
        default=None,
        help="UUID used for staging import rows and staging.legacy_id_map.migration_run_id.",
    )
    parser.add_argument("--report-json-path", type=Path, default=None, help="Optional JSON report output path.")
    parser.add_argument("--report-md-path", type=Path, default=None, help="Optional Markdown report output path.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Prepare PostgreSQL partitions and upsert staging.legacy_id_map. Requires FIN_OPS_POSTGRES_MIGRATION_URL.",
    )
    parser.add_argument(
        "--database-url-env",
        default="FIN_OPS_POSTGRES_MIGRATION_URL",
        help="Environment variable containing the PostgreSQL URL. The URL is never printed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    staging_plan = AppMongoStagingImportBuilder().build_plan(
        export_dir=args.export_dir,
        migration_run_id=args.migration_run_id,
    )
    report = AppMongoMigrationDryRunBuilder().build_report(
        export_dir=args.export_dir,
        staging_plan=staging_plan,
        migration_run_id=args.migration_run_id,
    )
    if args.report_json_path is not None:
        args.report_json_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_json_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.report_md_path is not None:
        args.report_md_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_md_path.write_text(report.to_markdown(), encoding="utf-8")

    if report.has_blockers:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "go_no_go": "NO_GO",
                    "blocking_findings": len(report.findings),
                    "migration_run_id": report.migration_run_id,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
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
            MigrationDryRunExecutor().execute(connection, report)

    print(
        json.dumps(
            {
                "status": "passed",
                "go_no_go": "GO",
                "executed": bool(args.execute),
                "migration_run_id": report.migration_run_id,
                "target_row_count": len(report.target_rows),
                "legacy_id_map_row_count": len(report.legacy_id_map_rows),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
