from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository


DEFAULT_LIMIT = 20


EXPLAIN_PROBES: tuple[tuple[str, str], ...] = (
    (
        "active_read_model_dirty_scopes",
        """
        select count(*)::bigint
        from job.read_model_dirty_scopes
        where tenant_id = 'default'
          and status in ('pending', 'processing', 'failed')
        """,
    ),
    (
        "active_read_model_outbox",
        """
        select count(*)::bigint
        from job.outbox_events
        where event_type like '%%.read_model.refresh'
          and status in ('pending', 'processing', 'failed', 'dead_lettered')
        """,
    ),
    (
        "non_fresh_app_status_readiness",
        """
        select count(*)::bigint
        from read_model.app_status_readiness
        where tenant_id = 'default'
          and status <> 'fresh'
        """,
    ),
    (
        "workbench_groups_all_scope_count",
        """
        select count(*)::bigint
        from read_model.workbench_groups
        where scope_key = 'all'
        """,
    ),
    (
        "workbench_group_rows_all_scope_count",
        """
        select count(*)::bigint
        from read_model.workbench_group_rows
        where scope_key = 'all'
        """,
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a read-only production sync SLO baseline from PostgreSQL runtime facts.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum rows for table/index/top SQL lists.")
    parser.add_argument(
        "--include-explain",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Collect EXPLAIN FORMAT JSON for fixed sync hot-path probes.",
    )
    parser.add_argument(
        "--analyze-explain",
        action="store_true",
        help="Use EXPLAIN ANALYZE. Default is plain EXPLAIN to keep the collector read-only and low impact.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    payload = collect_baseline(
        connection,
        limit=max(1, int(args.limit)),
        include_explain=bool(args.include_explain),
        analyze_explain=bool(args.analyze_explain),
    )
    print(json.dumps(payload, default=str, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def collect_baseline(
    connection: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    include_explain: bool = True,
    analyze_explain: bool = False,
) -> dict[str, Any]:
    runtime = RuntimeMonitoringRepository(connection)
    normalized_limit = max(1, int(limit))
    return {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "read_only" if not analyze_explain else "read_only_with_explain_analyze",
        "slo_targets": {
            "page_first_response_p95_ms": 1000,
            "light_read_model_enqueue_to_fresh_p95_ms": 3000,
            "heavy_workbench_local_convergence_p95_ms": [10000, 15000],
        },
        "runtime_health": _safe_section(lambda: runtime.health_summary()),
        "runtime_snapshot": _runtime_attention_snapshot(runtime),
        "dashboard_read_models": _safe_section(runtime.dashboard_read_model_metrics),
        "dashboard_workers": _safe_section(runtime.dashboard_worker_metrics),
        "dashboard_queues": _safe_section(runtime.dashboard_queue_metrics),
        "dashboard_outbox": _safe_section(runtime.dashboard_outbox_metric),
        "postgres_connections": _safe_section(lambda: _postgres_connections(connection)),
        "postgres_table_sizes": _safe_section(lambda: _postgres_table_sizes(connection, limit=normalized_limit)),
        "postgres_index_usage": _safe_section(lambda: _postgres_index_usage(connection, limit=normalized_limit)),
        "pg_stat_statements": _safe_section(lambda: _pg_stat_statements(connection, limit=normalized_limit)),
        "explain_probes": (
            _safe_section(lambda: _explain_probes(connection, analyze=analyze_explain))
            if include_explain
            else {"status": "skipped", "reason": "include_explain_false"}
        ),
        "api_performance": {
            "status": "not_collected",
            "reason": "api p95 is process-local dashboard/authenticated endpoint data; collect with logged-in HTTP sampling.",
        },
    }


def _safe_section(loader: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"status": "available", "data": loader()}
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc) or exc.__class__.__name__}


def _runtime_attention_snapshot(runtime: RuntimeMonitoringRepository) -> dict[str, Any]:
    section = _safe_section(runtime.app_status_runtime_snapshot)
    if section.get("status") != "available":
        return section
    snapshot = section.get("data") if isinstance(section.get("data"), dict) else {}
    return {
        "status": "available",
        "data": {
            "read_model_attention": _attention_items(snapshot.get("read_model_statuses")),
            "outbox_attention": _attention_items(snapshot.get("outbox_statuses")),
            "worker_attention": _attention_items(snapshot.get("worker_statuses")),
        },
    }


def _attention_items(group: object) -> dict[str, Any]:
    if not isinstance(group, dict):
        return {}
    ready_statuses = {"available", "fresh", "ready", "healthy"}
    return {
        str(key): value
        for key, value in group.items()
        if isinstance(value, dict) and str(value.get("status") or "").strip().lower() not in ready_statuses
    }


def _postgres_connections(connection: Any) -> dict[str, Any]:
    total = connection.fetch_one(
        """
        select
          count(*)::bigint as total_connections,
          count(*) filter (where state = 'active')::bigint as active_connections,
          count(*) filter (where wait_event is not null)::bigint as waiting_connections,
          current_setting('max_connections')::integer as max_connections
        from pg_stat_activity
        """
    ) or {}
    by_state = connection.fetch_all(
        """
        select coalesce(state, 'unknown') as state, count(*)::bigint as count
        from pg_stat_activity
        group by coalesce(state, 'unknown')
        order by count desc, state
        """
    )
    by_application = connection.fetch_all(
        """
        select coalesce(nullif(application_name, ''), 'unknown') as application_name, count(*)::bigint as count
        from pg_stat_activity
        group by coalesce(nullif(application_name, ''), 'unknown')
        order by count desc, application_name
        limit 20
        """
    )
    return {
        **_normalize_row(total),
        "by_state": [_normalize_row(row) for row in by_state],
        "by_application": [_normalize_row(row) for row in by_application],
    }


def _postgres_table_sizes(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          n.nspname as schema_name,
          c.relname as table_name,
          c.relkind,
          pg_total_relation_size(c.oid)::bigint as total_bytes,
          pg_relation_size(c.oid)::bigint as table_bytes,
          coalesce(s.n_live_tup, c.reltuples)::bigint as estimated_rows,
          s.seq_scan,
          s.idx_scan,
          s.n_tup_ins,
          s.n_tup_upd,
          s.n_tup_del
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        left join pg_stat_user_tables s on s.relid = c.oid
        where n.nspname in ('read_model', 'job', 'app')
          and c.relkind in ('r', 'm', 'p')
        order by pg_total_relation_size(c.oid) desc, n.nspname, c.relname
        limit %s
        """,
        (limit,),
    )
    return [_normalize_row(row) for row in rows]


def _postgres_index_usage(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          schemaname as schema_name,
          relname as table_name,
          indexrelname as index_name,
          pg_relation_size(indexrelid)::bigint as index_bytes,
          idx_scan,
          idx_tup_read,
          idx_tup_fetch
        from pg_stat_user_indexes
        where schemaname in ('read_model', 'job', 'app')
        order by pg_relation_size(indexrelid) desc, schemaname, relname, indexrelname
        limit %s
        """,
        (limit,),
    )
    return [_normalize_row(row) for row in rows]


def _pg_stat_statements(connection: Any, *, limit: int) -> dict[str, Any]:
    extension = connection.fetch_one(
        "select exists(select 1 from pg_extension where extname = 'pg_stat_statements') as installed"
    ) or {}
    if not bool(extension.get("installed")):
        return {"installed": False, "rows": []}
    try:
        rows = connection.fetch_all(
            """
            select
              query,
              calls,
              total_exec_time,
              mean_exec_time,
              rows
            from pg_stat_statements
            order by total_exec_time desc
            limit %s
            """,
            (limit,),
        )
        metric_version = "pg_stat_statements_total_exec_time"
    except Exception:
        rows = connection.fetch_all(
            """
            select
              query,
              calls,
              total_time as total_exec_time,
              mean_time as mean_exec_time,
              rows
            from pg_stat_statements
            order by total_time desc
            limit %s
            """,
            (limit,),
        )
        metric_version = "pg_stat_statements_total_time"
    return {
        "installed": True,
        "metric_version": metric_version,
        "rows": [_pg_stat_statement_row(row) for row in rows],
    }


def _pg_stat_statement_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_row(row)
    query = " ".join(str(normalized.get("query") or "").split())
    normalized["query"] = query[:500]
    return normalized


def _explain_probes(connection: Any, *, analyze: bool) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            **_explain_one(connection, sql=sql, analyze=analyze),
        }
        for name, sql in EXPLAIN_PROBES
    ]


def _explain_one(connection: Any, *, sql: str, analyze: bool) -> dict[str, Any]:
    mode = "analyze, buffers, format json" if analyze else "buffers, format json"
    row = connection.fetch_one(f"explain ({mode}) {sql}") or {}
    raw_plan = row.get("QUERY PLAN") or row.get("query_plan")
    if raw_plan is None and row:
        raw_plan = next(iter(row.values()))
    plan_document = raw_plan[0] if isinstance(raw_plan, list) and raw_plan else raw_plan
    if not isinstance(plan_document, dict):
        return {"plan": raw_plan}
    root_plan = plan_document.get("Plan") if isinstance(plan_document.get("Plan"), dict) else {}
    return {
        "planning_time_ms": plan_document.get("Planning Time"),
        "execution_time_ms": plan_document.get("Execution Time"),
        "node_type": root_plan.get("Node Type"),
        "startup_cost": root_plan.get("Startup Cost"),
        "total_cost": root_plan.get("Total Cost"),
        "plan_rows": root_plan.get("Plan Rows"),
        "plan_width": root_plan.get("Plan Width"),
        "plan": plan_document,
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in dict(row or {}).items():
        normalized[str(key)] = _json_safe(value)
    return normalized


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
