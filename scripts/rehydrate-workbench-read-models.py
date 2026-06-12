#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
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
    script_started_at = perf_counter()
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
        "timings": [],
    }
    if args.dry_run:
        status_started_at = perf_counter()
        report["status"] = repository.get_workbench_refresh_status(scope_key="all")
        report["timings"].append({"step": "dry_run_status", "duration_ms": _duration_ms(status_started_at)})
        report["duration_ms"] = _duration_ms(script_started_at)
        return _print_report(report, json_output=args.json)

    for scope_key in scopes:
        rebuild_started_at = perf_counter()
        result = builder.rebuild_workbench_read_model_scope(scope_key)
        rebuild_duration_ms = _duration_ms(rebuild_started_at)
        status_started_at = perf_counter()
        status = repository.get_workbench_refresh_status(scope_key=scope_key)
        status_duration_ms = _duration_ms(status_started_at)
        if str(status.get("read_model_status") or "").strip() == "failed":
            raise RuntimeError(str(status.get("last_error") or f"Workbench scope {scope_key} failed consistency validation."))
        complete_started_at = perf_counter()
        completed_dirty_scope = False
        if queue_repository.complete_read_model_refresh(
            tenant_id="default",
            scope_type="workbench",
            scope_key=scope_key,
        ):
            completed_dirty_scope = True
            report["completed_dirty_scopes"].append(scope_key)
        complete_duration_ms = _duration_ms(complete_started_at)
        scope_timings = {
            "rebuild_ms": rebuild_duration_ms,
            "status_ms": status_duration_ms,
            "complete_dirty_scope_ms": complete_duration_ms,
            "completed_dirty_scope": completed_dirty_scope,
        }
        report["timings"].append({"step": "scope", "scope_key": scope_key, **scope_timings})
        report["rebuilt"].append({"scope_key": scope_key, "result": result, "status": status, "timings": scope_timings})

    all_started_at = perf_counter()
    all_result = builder.refresh_workbench_all_scope_from_active_shards("all")
    all_duration_ms = _duration_ms(all_started_at)
    all_status_started_at = perf_counter()
    all_status = repository.get_workbench_refresh_status(scope_key="all")
    all_status_duration_ms = _duration_ms(all_status_started_at)
    if str(all_status.get("read_model_status") or "").strip() == "failed":
        raise RuntimeError(str(all_status.get("last_error") or "Workbench all-scope generation failed consistency validation."))
    complete_all_started_at = perf_counter()
    completed_all_dirty_scope = False
    if queue_repository.complete_read_model_refresh(
        tenant_id="default",
        scope_type="workbench",
        scope_key="all",
    ):
        completed_all_dirty_scope = True
        report["completed_dirty_scopes"].append("all")
    complete_all_duration_ms = _duration_ms(complete_all_started_at)
    report["all"] = all_result
    report["timings"].append(
        {
            "step": "all",
            "rebuild_ms": all_duration_ms,
            "status_ms": all_status_duration_ms,
            "complete_dirty_scope_ms": complete_all_duration_ms,
            "completed_dirty_scope": completed_all_dirty_scope,
        }
    )
    final_status_started_at = perf_counter()
    report["status"] = repository.get_workbench_refresh_status(scope_key="all")
    report["timings"].append({"step": "final_status", "duration_ms": _duration_ms(final_status_started_at)})
    report["duration_ms"] = _duration_ms(script_started_at)
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


def _duration_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


if __name__ == "__main__":
    raise SystemExit(main())
