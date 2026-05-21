from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare legacy cost statistics explorer output with SQL read model payload.")
    parser.add_argument("--month", default="all", help="Month scope, for example all or 2026-05.")
    parser.add_argument("--project-scope", default="active", choices=("active", "all"))
    return parser


def _sql_payload(connection: PostgresConnection, *, month: str, project_scope: str) -> dict[str, Any] | None:
    scope_key = f"{project_scope}:{month}"
    row = connection.fetch_one(
        """
        select payload, raw_payload
        from read_model.cost_statistics_read_models
        where scope_key = %s
        limit 1
        """,
        (scope_key,),
    )
    if not row:
        return None
    payload = row.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("normalized_payload"), dict):
        payload = payload.get("normalized_payload")
    return payload if isinstance(payload, dict) else None


def _summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"exists": False, "entry_count": 0, "total_amount": "0.00"}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "exists": True,
        "entry_count": len(payload.get("time_rows") or []),
        "total_amount": str(summary.get("total_amount") or "0.00"),
        "project_row_count": len(payload.get("project_rows") or []),
        "expense_type_row_count": len(payload.get("expense_type_rows") or []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    month = str(args.month or "all").strip() or "all"
    project_scope = str(args.project_scope or "active").strip() or "active"
    application = build_application()
    legacy_payload = application._cost_statistics_service.get_explorer(month, project_scope=project_scope)
    connection = PostgresConnection(PostgresSettings.from_env())
    sql_payload = _sql_payload(connection, month=month, project_scope=project_scope)
    legacy_summary = _summary(legacy_payload)
    sql_summary = _summary(sql_payload)
    payload = {
        "status": "ok" if legacy_summary == sql_summary else "mismatch",
        "month": month,
        "project_scope": project_scope,
        "legacy": legacy_summary,
        "sql": sql_summary,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
