from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare legacy tax offset month output with SQL read model payload.")
    parser.add_argument("--month", required=True, help="Month scope, for example 2026-05.")
    return parser


def _sql_payload(connection: PostgresConnection, *, month: str) -> dict[str, Any] | None:
    row = connection.fetch_one(
        """
        select payload, raw_payload
        from read_model.tax_offset_read_models
        where scope_key = %s
        limit 1
        """,
        (month,),
    )
    if not row:
        return None
    payload = row.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("normalized_payload"), dict):
        payload = payload.get("normalized_payload")
    return payload if isinstance(payload, dict) else None


def _summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "exists": False,
            "output_count": 0,
            "input_plan_count": 0,
            "certified_count": 0,
            "deductible_tax": "0.00",
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "exists": True,
        "output_count": len(payload.get("output_items") or []),
        "input_plan_count": len(payload.get("input_plan_items") or []),
        "certified_count": len(payload.get("certified_items") or []),
        "deductible_tax": str(summary.get("deductible_tax") or "0.00"),
        "result_amount": str(summary.get("result_amount") or "0.00"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    month = str(args.month or "").strip()
    application = build_application()
    legacy_payload = application._tax_api_routes.get_tax_offset(month)
    connection = PostgresConnection(PostgresSettings.from_env())
    sql_payload = _sql_payload(connection, month=month)
    legacy_summary = _summary(legacy_payload)
    sql_summary = _summary(sql_payload)
    payload = {
        "status": "ok" if legacy_summary == sql_summary else "mismatch",
        "month": month,
        "legacy": legacy_summary,
        "sql": sql_summary,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
