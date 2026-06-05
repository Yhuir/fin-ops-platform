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
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository  # noqa: E402
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository  # noqa: E402
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rehydrate Workbench SQL read models from PostgreSQL facts and publish all only after consistency checks pass."
    )
    parser.add_argument("--scope", action="append", default=[], help="Month scope YYYY-MM. Repeatable. Defaults to all fact-backed months.")
    parser.add_argument("--dry-run", action="store_true", help="List scopes and current status without rebuilding.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument(
        "--statement-timeout-seconds",
        type=int,
        default=300,
        help="PostgreSQL statement timeout for rebuild queries. Defaults to 300 seconds.",
    )
    args = parser.parse_args()
    if args.statement_timeout_seconds <= 0:
        raise ValueError("--statement-timeout-seconds must be positive.")

    connection = PostgresConnection(PostgresSettings.from_env())
    connection.set_statement_timeout_ms(args.statement_timeout_seconds * 1000)
    repository = PostgresReadModelRepository(connection)
    queue_repository = RuntimeQueueRepository(connection)
    builder = WorkbenchSqlProjectionBuilder(connection=connection, read_model_repository=repository)
    scopes = _scope_keys(builder, args.scope)
    report: dict[str, Any] = {
        "action": "rehydrate_workbench_read_models",
        "dry_run": bool(args.dry_run),
        "scope_keys": scopes,
        "rebuilt": [],
        "completed_dirty_scopes": [],
        "all": None,
        "status": None,
    }
    if args.dry_run:
        report["status"] = repository.get_workbench_refresh_status(scope_key="all")
        return _print_report(report, json_output=args.json)

    for scope_key in scopes:
        result = builder.rebuild_workbench_read_model_scope(scope_key)
        status = repository.get_workbench_refresh_status(scope_key=scope_key)
        if str(status.get("read_model_status") or "").strip() == "failed":
            raise RuntimeError(str(status.get("last_error") or f"Workbench scope {scope_key} failed consistency validation."))
        if queue_repository.complete_read_model_refresh(
            tenant_id="default",
            scope_type="workbench",
            scope_key=scope_key,
        ):
            report["completed_dirty_scopes"].append(scope_key)
        report["rebuilt"].append({"scope_key": scope_key, "result": result, "status": status})

    all_result = builder.refresh_workbench_all_scope_from_active_shards("all")
    all_status = repository.get_workbench_refresh_status(scope_key="all")
    if str(all_status.get("read_model_status") or "").strip() == "failed":
        raise RuntimeError(str(all_status.get("last_error") or "Workbench all-scope generation failed consistency validation."))
    if queue_repository.complete_read_model_refresh(
        tenant_id="default",
        scope_type="workbench",
        scope_key="all",
    ):
        report["completed_dirty_scopes"].append("all")
    report["all"] = all_result
    report["status"] = repository.get_workbench_refresh_status(scope_key="all")
    return _print_report(report, json_output=args.json)


def _scope_keys(builder: WorkbenchSqlProjectionBuilder, requested: list[str]) -> list[str]:
    if requested:
        return sorted(dict.fromkeys(str(scope).strip() for scope in requested if str(scope).strip()))
    return list(builder.list_workbench_scope_shards("all"))


def _print_report(report: dict[str, Any], *, json_output: bool) -> int:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
