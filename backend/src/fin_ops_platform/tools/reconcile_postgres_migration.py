from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

from fin_ops_platform.postgres.migrate import MigrationError, database_url_from_env_or_arg, run_psql


CORE_EXPECTED = {
    "import_batches": ("app.import_batches", None),
    "import_batches:row_results": ("app.import_batch_rows", None),
    "file_objects": ("app.file_objects", None),
    "file_import_files": ("app.import_files", None),
    "invoices": ("app.invoices", None),
    "bank_transactions": ("app.bank_transactions", None),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build stage 04 PostgreSQL reconciliation report.")
    parser.add_argument("--export-id", required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--report-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = reconcile_postgres_migration(
            export_id=args.export_id,
            database_url=args.database_url,
            report_dir=args.report_dir,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary with sanitized output.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def reconcile_postgres_migration(*, export_id: str, database_url: str | None, report_dir: Path) -> dict[str, Any]:
    resolved_database_url = database_url_from_env_or_arg(database_url)
    export_row = fetch_one_json(
        resolved_database_url,
        f"""
select json_build_object(
  'export_id', export_id,
  'source_database', source_database,
  'status', status,
  'manifest', manifest
)::text
from staging.mongo_exports
where export_id = {sql_literal(export_id)};
""",
    )
    if not export_row:
        raise MigrationError(f"staging export not found: {export_id}")
    manifest = export_row.get("manifest") or {}
    source_counts = fetch_counts(
        resolved_database_url,
        f"""
select source_collection, count(*)::bigint
from staging.mongo_raw_records r
join staging.mongo_exports e on e.id = r.export_id
where e.export_id = {sql_literal(export_id)}
group by source_collection
order by source_collection;
""",
    )
    target_counts = fetch_table_counts(resolved_database_url)
    mismatches: list[dict[str, Any]] = []
    for source_collection, (target_table, _) in CORE_EXPECTED.items():
        expected = source_counts.get(source_collection, 0)
        actual = target_counts.get(target_table, 0)
        if expected != actual:
            mismatches.append(
                {
                    "kind": "core_count_mismatch",
                    "source_collection": source_collection,
                    "target_table": target_table,
                    "expected": expected,
                    "actual": actual,
                }
            )
    source_total = sum(source_counts.values())
    manifest_total = int(manifest.get("total_records") or 0)
    if manifest_total and source_total != manifest_total:
        mismatches.append({"kind": "staging_manifest_count_mismatch", "expected": manifest_total, "actual": source_total})
    amount_checks = fetch_amount_checks(resolved_database_url)
    id_mapping_checks = fetch_mapping_checks(resolved_database_url, export_id)
    mismatches.extend(mapping_mismatches(id_mapping_checks))
    report = {
        "status": "pass" if not mismatches else "blocked",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "export_id": export_id,
        "source_database": export_row.get("source_database"),
        "manifest_sha256": manifest.get("manifest_sha256"),
        "manifest_total_records": manifest_total,
        "source_counts": source_counts,
        "target_counts": target_counts,
        "core_amount_checks": amount_checks,
        "id_mapping_checks": id_mapping_checks,
        "gridfs": manifest.get("gridfs") or {},
        "mismatches": mismatches,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{export_id}.stage04.reconciliation.json"
    md_path = report_dir / f"{export_id}.stage04.reconciliation.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    return {**report, "report_json": str(json_path), "report_markdown": str(md_path)}


def fetch_one_json(database_url: str, sql: str) -> dict[str, Any] | None:
    row = run_psql(database_url, sql=sql).strip()
    return json.loads(row) if row else None


def fetch_counts(database_url: str, sql: str) -> dict[str, int]:
    rows = run_psql(database_url, sql=sql)
    counts: dict[str, int] = {}
    for line in rows.splitlines():
        if not line:
            continue
        key, count = line.split("|", 1)
        counts[key] = int(count)
    return counts


def fetch_table_counts(database_url: str) -> dict[str, int]:
    tables = [
        "app.import_batches",
        "app.import_batch_rows",
        "app.file_objects",
        "app.import_files",
        "app.invoices",
        "app.bank_transactions",
        "app.workbench_pair_relations",
        "app.workbench_exception_cases",
        "app.no_oa_bank_batches",
        "job.background_jobs",
        "read_model.workbench_candidate_matches",
        "read_model.search_index_rows",
    ]
    sql = "\nunion all\n".join(f"select {sql_literal(table)}, count(*)::bigint from {table}" for table in tables) + ";"
    return fetch_counts(database_url, sql)


def fetch_amount_checks(database_url: str) -> dict[str, Any]:
    return {
        "invoices": fetch_one_json(
            database_url,
            """
select json_build_object(
  'count', count(*),
  'amount_sum', coalesce(sum(amount), 0)::text,
  'signed_amount_sum', coalesce(sum(signed_amount), 0)::text,
  'written_off_sum', coalesce(sum(written_off_amount), 0)::text
)::text
from app.invoices;
""",
        ),
        "bank_transactions": fetch_one_json(
            database_url,
            """
select json_build_object(
  'count', count(*),
  'amount_sum', coalesce(sum(amount), 0)::text,
  'signed_amount_sum', coalesce(sum(signed_amount), 0)::text,
  'inflow_sum', coalesce(sum(case when txn_direction = 'inflow' then amount else 0 end), 0)::text,
  'outflow_sum', coalesce(sum(case when txn_direction = 'outflow' then amount else 0 end), 0)::text
)::text
from app.bank_transactions;
""",
        ),
    }


def fetch_mapping_checks(database_url: str, export_id: str) -> dict[str, int]:
    rows = fetch_one_json(
        database_url,
        f"""
select json_build_object(
  'total_mappings', count(*),
  'current_export_mappings', count(*) filter (where raw_payload->>'export_id' = {sql_literal(export_id)}),
  'stale_mappings', count(*) filter (where raw_payload->>'export_id' is not null and raw_payload->>'export_id' <> {sql_literal(export_id)}),
  'conflicting_mappings', 0
)::text
from staging.id_mappings;
""",
    )
    return {key: int(value or 0) for key, value in (rows or {}).items()}


def mapping_mismatches(id_mapping_checks: dict[str, int]) -> list[dict[str, Any]]:
    conflicts = int(id_mapping_checks.get("conflicting_mappings") or 0)
    if conflicts:
        return [{"kind": "id_mapping_conflicts", "actual": conflicts}]
    return []


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Stage 04 Reconciliation - {report['export_id']}",
        "",
        f"- status: `{report['status']}`",
        f"- generated_at: `{report['generated_at']}`",
        f"- source_database: `{report.get('source_database')}`",
        f"- manifest_sha256: `{report.get('manifest_sha256')}`",
        f"- manifest_total_records: `{report.get('manifest_total_records')}`",
        "",
        "## Core Counts",
        "",
    ]
    for source_collection, (target_table, _) in CORE_EXPECTED.items():
        lines.append(
            f"- `{source_collection}` -> `{target_table}`: source `{report['source_counts'].get(source_collection, 0)}`, target `{report['target_counts'].get(target_table, 0)}`"
        )
    lines.extend(["", "## Mismatches", ""])
    if report["mismatches"]:
        for mismatch in report["mismatches"]:
            lines.append(f"- `{mismatch['kind']}`: `{json.dumps(mismatch, ensure_ascii=False, sort_keys=True)}`")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def sql_literal(value: object) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
