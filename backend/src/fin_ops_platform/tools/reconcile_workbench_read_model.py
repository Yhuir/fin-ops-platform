from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare legacy workbench builder row ids with SQL read_model.workbench_rows.")
    parser.add_argument("--scope-key", default="all", help="Workbench scope key, for example all or 2026-05.")
    return parser


def _row_ids_from_grouped_payload(payload: dict[str, Any]) -> set[str]:
    row_ids: set[str] = set()

    def scan_group(group: Any) -> None:
        if not isinstance(group, dict):
            return
        for key, value in group.items():
            if not str(key).endswith("_rows") or not isinstance(value, list):
                continue
            for row in value:
                if not isinstance(row, dict):
                    continue
                row_id = str(row.get("id") or row.get("row_id") or "").strip()
                if row_id:
                    row_ids.add(row_id)

    for section_name in ("paired", "open", "ignored"):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        groups = section.get("groups")
        if isinstance(groups, list):
            for group in groups:
                scan_group(group)
        else:
            scan_group(section)
    return row_ids


def _legacy_builder_row_ids(scope_key: str) -> set[str]:
    application = build_application()
    base_scope_key = application._workbench_read_model_base_scope_key(scope_key)
    raw_payload = application._build_raw_workbench_payload(base_scope_key)
    candidate_payload = application._apply_candidate_matches_to_payload(raw_payload, base_scope_key)
    grouped_payload = application._group_row_payload(
        candidate_payload,
        turnover_relations=application._active_turnover_relations_for_workbench(),
    )
    return _row_ids_from_grouped_payload(grouped_payload)


def _sql_row_ids(connection: PostgresConnection, scope_key: str) -> set[str]:
    rows = connection.fetch_all(
        """
        select row_id
        from read_model.workbench_rows
        where scope_key = %s
        order by row_id
        """,
        (scope_key,),
    )
    return {str(row.get("row_id") or "").strip() for row in rows if str(row.get("row_id") or "").strip()}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scope_key = str(args.scope_key or "all").strip() or "all"
    connection = PostgresConnection(PostgresSettings.from_env())
    legacy_row_ids = _legacy_builder_row_ids(scope_key)
    sql_row_ids = _sql_row_ids(connection, scope_key)
    missing_in_sql = sorted(legacy_row_ids - sql_row_ids)
    extra_in_sql = sorted(sql_row_ids - legacy_row_ids)
    payload = {
        "status": "ok" if not missing_in_sql and not extra_in_sql else "mismatch",
        "scope_key": scope_key,
        "legacy_row_count": len(legacy_row_ids),
        "sql_row_count": len(sql_row_ids),
        "missing_in_sql": missing_in_sql[:100],
        "extra_in_sql": extra_in_sql[:100],
        "truncated": len(missing_in_sql) > 100 or len(extra_in_sql) > 100,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
