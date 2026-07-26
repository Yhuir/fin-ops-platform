#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile SQL-native runtime read models and optionally capture hot-path EXPLAIN plans."
    )
    parser.add_argument("--scope-key", default="2025-12", help="Workbench/month scope to inspect, for example 2026-05.")
    parser.add_argument("--legacy-workbench-json", default=None, help="Optional legacy/shadow workbench JSON export to compare row ids.")
    parser.add_argument("--explain", action="store_true", help="Include EXPLAIN (FORMAT JSON) for hot SQL read paths.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    args = parser.parse_args()

    connection = PostgresConnection(PostgresSettings.from_env())
    report = build_report(
        connection,
        scope_key=str(args.scope_key or "").strip() or "2025-12",
        legacy_workbench_json=Path(args.legacy_workbench_json) if args.legacy_workbench_json else None,
        include_explain=bool(args.explain),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print_human_report(report)
    return 0 if not report.get("errors") else 2


def build_report(
    connection: PostgresConnection,
    *,
    scope_key: str,
    legacy_workbench_json: Path | None,
    include_explain: bool,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "scope_key": scope_key,
        "workbench": workbench_report(connection, scope_key),
        "tax_offset": table_count_report(connection, "read_model.tax_offset_read_models", scope_key),
        "queue": queue_report(connection),
        "errors": [],
    }
    if legacy_workbench_json is not None:
        report["legacy_workbench_compare"] = compare_legacy_workbench_json(
            connection,
            scope_key=scope_key,
            path=legacy_workbench_json,
        )
    if include_explain:
        report["explain"] = explain_report(connection, scope_key)
    return report


def workbench_report(connection: PostgresConnection, scope_key: str) -> dict[str, Any]:
    snapshot = connection.fetch_one(
        """
        select scope_key, row_count, generated_at, cache_status, source_versions
        from read_model.workbench_snapshots
        where scope_key = %s
        """,
        (scope_key,),
    )
    rows_by_status = connection.fetch_all(
        """
        select status, count(*) as count
        from read_model.workbench_rows
        where scope_key = %s
        group by status
        order by status
        """,
        (scope_key,),
    )
    rows_by_kind = connection.fetch_all(
        """
        select source_kind, count(*) as count
        from read_model.workbench_rows
        where scope_key = %s
        group by source_kind
        order by source_kind
        """,
        (scope_key,),
    )
    relation_rows = connection.fetch_all(
        """
        select status, count(*) as count
        from app.workbench_pair_relations
        where to_char(month_scope, 'YYYY-MM') = %s
        group by status
        order by status
        """,
        (scope_key,),
    )
    return {
        "snapshot": dict(snapshot) if isinstance(snapshot, dict) else None,
        "rows_by_status": rows_by_key(rows_by_status, "status"),
        "rows_by_source_kind": rows_by_key(rows_by_kind, "source_kind"),
        "formal_relations_by_status": rows_by_key(relation_rows, "status"),
    }


def table_count_report(connection: PostgresConnection, table_name: str, scope_key: str) -> dict[str, Any]:
    row = connection.fetch_one(
        f"""
        select count(*) as rows, coalesce(sum(entry_count), 0) as entry_count
        from {table_name}
        where scope_key = %s or %s = 'all'
        """,
        (scope_key, scope_key),
    )
    return dict(row) if isinstance(row, dict) else {"rows": 0, "entry_count": 0}


def queue_report(connection: PostgresConnection) -> dict[str, Any]:
    outbox = connection.fetch_all(
        """
        select status, count(*) as count
        from job.outbox_events
        where status in ('pending', 'processing', 'failed')
        group by status
        order by status
        """
    )
    dirty = connection.fetch_all(
        """
        select scope_type, status, count(*) as count
        from job.read_model_dirty_scopes
        where status in ('pending', 'processing', 'failed')
        group by scope_type, status
        order by scope_type, status
        """
    )
    return {
        "outbox_events": rows_by_key(outbox, "status"),
        "dirty_scopes": [
            {"scope_type": row.get("scope_type"), "status": row.get("status"), "count": int(row.get("count") or 0)}
            for row in dirty
        ],
    }


def compare_legacy_workbench_json(
    connection: PostgresConnection,
    *,
    scope_key: str,
    path: Path,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    legacy_row_ids = extract_workbench_row_ids(payload)
    sql_rows = connection.fetch_all(
        "select row_id from read_model.workbench_rows where scope_key = %s order by row_id",
        (scope_key,),
    )
    sql_row_ids = {str(row.get("row_id") or "") for row in sql_rows if str(row.get("row_id") or "")}
    return {
        "legacy_file": str(path),
        "legacy_row_count": len(legacy_row_ids),
        "sql_row_count": len(sql_row_ids),
        "missing_in_sql": sorted(legacy_row_ids - sql_row_ids)[:100],
        "extra_in_sql": sorted(sql_row_ids - legacy_row_ids)[:100],
        "truncated": len(legacy_row_ids - sql_row_ids) > 100 or len(sql_row_ids - legacy_row_ids) > 100,
    }


def extract_workbench_row_ids(payload: Any) -> set[str]:
    row_ids: set[str] = set()

    def scan(value: Any) -> None:
        if isinstance(value, dict):
            row_id = value.get("id") or value.get("row_id")
            row_type = value.get("type") or value.get("source_kind")
            if row_id and row_type:
                row_ids.add(str(row_id))
            for child in value.values():
                scan(child)
        elif isinstance(value, list):
            for item in value:
                scan(item)

    scan(payload)
    return row_ids


def explain_report(connection: PostgresConnection, scope_key: str) -> dict[str, Any]:
    return {
        "workbench_page": explain(
            connection,
            """
            select row_id, source_kind, status, payload
            from read_model.workbench_rows
            where scope_key = %s and status = %s
            order by updated_at desc, row_id
            limit 50
            """,
            (scope_key, "open"),
        ),
        "search_index": explain(
            connection,
            """
            select row_id, source_kind, payload
            from read_model.search_index_rows
            where searchable_text ilike %s
            order by updated_at desc, row_id
            limit 50
            """,
            ("%发票%",),
        ),
        "pending_invoice": explain(
            connection,
            """
            select row_id, payload
            from read_model.pending_invoice_rows
            where direction = %s and filter_group = %s
            order by trade_date desc, row_id
            limit 50
            """,
            ("expense", "all"),
        ),
        "tax_offset": explain(
            connection,
            """
            select scope_key, entry_count, payload
            from read_model.tax_offset_read_models
            where scope_key = %s
            """,
            (scope_key,),
        ),
    }


def explain(connection: PostgresConnection, sql: str, params: tuple[Any, ...]) -> Any:
    rows = connection.fetch_all(f"explain (format json) {sql}", params)
    if not rows:
        return None
    row = rows[0]
    return row.get("QUERY PLAN") or row.get("query plan") or row


def rows_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return {str(row.get(key) or ""): int(row.get("count") or 0) for row in rows}


def print_human_report(report: dict[str, Any]) -> None:
    print(f"scope_key: {report['scope_key']}")
    print("workbench:")
    print(json.dumps(report["workbench"], ensure_ascii=False, indent=2, sort_keys=True, default=str))
    print("tax_offset:")
    print(json.dumps(report["tax_offset"], ensure_ascii=False, indent=2, sort_keys=True, default=str))
    print("queue:")
    print(json.dumps(report["queue"], ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if "legacy_workbench_compare" in report:
        print("legacy_workbench_compare:")
        print(json.dumps(report["legacy_workbench_compare"], ensure_ascii=False, indent=2, sort_keys=True))
    if "explain" in report:
        print("explain:")
        print(json.dumps(report["explain"], ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
