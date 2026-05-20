from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from fin_ops_platform.postgres.migrate import MigrationError, database_url_from_env_or_arg, run_psql
from fin_ops_platform.tools.import_postgres_staging import REQUIRED_MIGRATIONS, assert_required_migrations
from fin_ops_platform.tools.postgres_transform import (
    ALL_DOMAINS,
    TARGET_TABLES,
    StagingRecord,
    build_transaction_sql,
    build_transform_plan,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transform stage 03 PostgreSQL staging rows into normalized PostgreSQL tables.")
    parser.add_argument("--export-id", required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-domain", action="append", choices=ALL_DOMAINS)
    parser.add_argument("--skip-domain", action="append", choices=ALL_DOMAINS)
    parser.add_argument("--fail-on-warning", action="store_true")
    parser.add_argument("--replace-existing-target", action="store_true", help="Reserved for a later controlled rebuild path; currently blocked.")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args(argv)

    try:
        result = transform_staging_to_postgres(
            export_id=args.export_id,
            database_url=args.database_url,
            dry_run=args.dry_run,
            only_domains=set(args.only_domain or []),
            skip_domains=set(args.skip_domain or []),
            fail_on_warning=args.fail_on_warning,
            replace_existing_target=args.replace_existing_target,
            report_dir=args.report_dir,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary with sanitized output.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def transform_staging_to_postgres(
    *,
    export_id: str,
    database_url: str | None,
    dry_run: bool,
    only_domains: set[str],
    skip_domains: set[str],
    fail_on_warning: bool,
    replace_existing_target: bool,
    report_dir: Path | None,
) -> dict[str, Any]:
    if replace_existing_target:
        raise MigrationError("--replace-existing-target is intentionally blocked in stage 04 until same-export proof is implemented.")
    resolved_database_url = database_url_from_env_or_arg(database_url)
    assert_required_migrations(resolved_database_url)
    export_row = fetch_export_row(resolved_database_url, export_id)
    records = fetch_staging_records(resolved_database_url, export_id)
    target_counts = fetch_target_counts(resolved_database_url)
    plan = build_transform_plan(
        export_row=export_row,
        records=records,
        target_counts=target_counts,
        only_domains=only_domains or None,
        skip_domains=skip_domains or None,
    )
    if fail_on_warning and plan.warnings:
        plan.blockers.append("warnings_present")
    output = plan.to_dict(dry_run=dry_run)
    output["required_migrations"] = list(REQUIRED_MIGRATIONS)
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / f"{export_id}.stage04.plan.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if plan.blockers:
        raise MigrationError("Stage 04 preflight blocked: " + "; ".join(plan.blockers))
    if dry_run:
        return output
    sql = build_transaction_sql(plan)
    run_psql(resolved_database_url, sql=sql)
    return {**output, "status": "transformed"}


def fetch_export_row(database_url: str, export_id: str) -> dict[str, Any]:
    row = run_psql(
        database_url,
        sql=f"""
select json_build_object(
  'id', id,
  'export_id', export_id,
  'source_database', source_database,
  'status', status,
  'manifest', manifest
)::text
from staging.mongo_exports
where export_id = {sql_literal(export_id)};
""",
    ).strip()
    if not row:
        raise MigrationError(f"staging export not found: {export_id}")
    return json.loads(row)


def fetch_staging_records(database_url: str, export_id: str) -> list[StagingRecord]:
    rows = run_psql(
        database_url,
        sql=f"""
select json_build_object(
  'export_id', e.export_id,
  'source_collection', r.source_collection,
  'legacy_mongo_id', r.legacy_mongo_id,
  'record_type', r.record_type,
  'normalized_payload', r.normalized_payload,
  'raw_payload', r.raw_payload
)::text
from staging.mongo_raw_records r
join staging.mongo_exports e on e.id = r.export_id
where e.export_id = {sql_literal(export_id)}
order by r.source_collection, r.legacy_mongo_id nulls last, r.id::text;
""",
    )
    records: list[StagingRecord] = []
    for line in rows.splitlines():
        if not line:
            continue
        payload = json.loads(line)
        legacy_mongo_id = payload.get("legacy_mongo_id")
        if legacy_mongo_id in (None, ""):
            raise MigrationError(f"staging record missing legacy_mongo_id: {payload.get('source_collection')}")
        records.append(
            StagingRecord(
                export_id=str(payload["export_id"]),
                source_collection=str(payload["source_collection"]),
                legacy_mongo_id=str(legacy_mongo_id),
                record_type=payload.get("record_type"),
                normalized_payload=payload.get("normalized_payload") or {},
                raw_payload=payload.get("raw_payload") or {},
            )
        )
    return records


def fetch_target_counts(database_url: str) -> dict[str, int]:
    sql = "\nunion all\n".join(
        f"select {sql_literal(schema + '.' + table)} as table_name, count(*)::bigint as row_count from {schema}.{table}"
        for schema, table in TARGET_TABLES
    )
    rows = run_psql(database_url, sql=sql + ";")
    counts: dict[str, int] = {}
    for line in rows.splitlines():
        if not line:
            continue
        table_name, row_count = line.split("|", 1)
        counts[table_name] = int(row_count)
    return counts


def sql_literal(value: object) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
