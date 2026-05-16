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

from fin_ops_platform.services.app_mongo_migration_dry_run import (
    AppMongoMigrationDryRunBuilder,
    MigrationDryRunExecutor,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a secret-free app Mongo staging -> PostgreSQL facts dry-run reconciliation report.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Directory containing 06A manifest.json and NDJSON files. No database access is required.",
    )
    source.add_argument(
        "--staging-rows-json",
        type=Path,
        default=None,
        help="JSON file with manifest_record and staging rows for report-only/validate-only checks.",
    )
    source.add_argument(
        "--from-postgres",
        action="store_true",
        help="Read staging.mongo_import_rows by --migration-run-id from an isolated PostgreSQL dry-run database.",
    )
    parser.add_argument(
        "--migration-run-id",
        default=None,
        help="UUID used for staging rows and staging.legacy_id_map.migration_run_id.",
    )
    parser.add_argument("--report-json-path", type=Path, default=None, help="Optional JSON report output path.")
    parser.add_argument("--report-md-path", type=Path, default=None, help="Optional Markdown report output path.")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate a report and exit without database writes. This is the default unless --execute is set.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the report shape and GO/NO_GO decision without database writes.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply partition preparation and staging.legacy_id_map only in an isolated dry-run database. Never writes production facts.",
    )
    parser.add_argument(
        "--database-url-env",
        default="FIN_OPS_POSTGRES_MIGRATION_URL",
        help="Environment variable containing the isolated PostgreSQL URL. The URL is never printed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    builder = AppMongoMigrationDryRunBuilder()
    if args.from_postgres:
        if not args.migration_run_id:
            raise RuntimeError("--from-postgres requires --migration-run-id")
        database_url = _database_url(args.database_url_env)
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required only when --from-postgres or --execute is used.") from exc
        with psycopg.connect(database_url) as connection:
            manifest_record, staging_rows = builder.load_staging_rows_from_postgres(
                connection=connection,
                migration_run_id=args.migration_run_id,
            )
        report = builder.build_report_from_staging_rows(
            migration_run_id=args.migration_run_id,
            staging_rows=staging_rows,
            manifest_record=manifest_record,
        )
    elif args.staging_rows_json is not None:
        payload = json.loads(args.staging_rows_json.read_text(encoding="utf-8"))
        manifest_record = payload.get("manifest_record") or {}
        staging_rows = payload.get("staging_rows") or payload.get("rows") or []
        if not isinstance(manifest_record, dict) or not isinstance(staging_rows, list):
            raise RuntimeError("--staging-rows-json must contain manifest_record object and staging_rows array.")
        migration_run_id = str(args.migration_run_id or manifest_record.get("id") or "")
        if not migration_run_id:
            raise RuntimeError("--staging-rows-json requires --migration-run-id or manifest_record.id.")
        report = builder.build_report_from_staging_rows(
            migration_run_id=migration_run_id,
            staging_rows=staging_rows,
            manifest_record=manifest_record,
        )
    else:
        if args.export_dir is None:
            raise RuntimeError("One source is required: --export-dir, --staging-rows-json, or --from-postgres.")
        report = builder.build_report(
            export_dir=args.export_dir,
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

    if args.execute:
        database_url = _database_url(args.database_url_env)
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required only when --execute is used.") from exc
        with psycopg.connect(database_url) as connection:
            MigrationDryRunExecutor().execute(connection, report)

    summary = {
        "status": "failed" if report.has_blockers else "passed",
        "go_no_go": report.decision["go_no_go"],
        "blocking_findings": len([item for item in report.findings if item.get("severity") == "error"]),
        "executed": bool(args.execute),
        "report_only": bool(args.report_only or args.validate_only or not args.execute),
        "migration_run_id": report.migration_run_id,
        "target_row_count": len(report.target_rows),
        "legacy_id_map_row_count": len(report.legacy_id_map_rows),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 2 if report.has_blockers else 0


def _database_url(env_name: str) -> str:
    database_url = os.getenv(env_name)
    if not database_url:
        raise RuntimeError(f"Missing PostgreSQL URL environment variable: {env_name}")
    return database_url


if __name__ == "__main__":
    raise SystemExit(main())
