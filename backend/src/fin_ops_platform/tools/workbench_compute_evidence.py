from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConfigurationError, PostgresConnection, PostgresSettings
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report, write_json_report


DEFAULT_LIMIT = 20
DEFAULT_WINDOW_HOURS = 24


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect read-only Workbench matching compute evidence for Go hot-path admission.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    parser.add_argument("--output", type=Path, help="Optional path to write the JSON report.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--window-hours", type=int, default=DEFAULT_WINDOW_HOURS)
    parser.add_argument(
        "--include-explain",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Collect plain EXPLAIN plans for fixed Workbench compute evidence probes.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        connection = PostgresConnection(PostgresSettings.from_env())
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(tool="workbench_compute_evidence", message=str(exc))
        report["production_evidence_required"] = True
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    report = collect_evidence(
        connection,
        tenant_id=str(args.tenant_id or "default"),
        limit=max(1, int(args.limit)),
        window_hours=max(1, int(args.window_hours)),
        include_explain=bool(args.include_explain),
    )
    write_json_report(report, output=args.output, stdout=stdout)
    return 0 if report.get("status") in {"available", "partial"} else 1


def collect_evidence(
    connection: Any,
    *,
    tenant_id: str = "default",
    limit: int = DEFAULT_LIMIT,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    include_explain: bool = True,
) -> dict[str, Any]:
    normalized_limit = max(1, int(limit))
    normalized_window_hours = max(1, int(window_hours))
    sections = {
        "matching_scope_durations": _safe_section(
            lambda: _matching_scope_durations(
                connection,
                tenant_id=tenant_id,
                window_hours=normalized_window_hours,
            )
        ),
        "matching_scope_samples": _safe_section(
            lambda: _matching_scope_samples(
                connection,
                tenant_id=tenant_id,
                window_hours=normalized_window_hours,
                limit=normalized_limit,
            )
        ),
        "worker_heartbeat": _safe_section(lambda: _worker_heartbeat(connection, limit=normalized_limit)),
        "formal_relation_counts": _safe_section(
            lambda: _formal_relation_counts(
                connection,
                tenant_id=tenant_id,
                window_hours=normalized_window_hours,
            )
        ),
        "active_generation_row_counts": _safe_section(
            lambda: _active_generation_row_counts(connection, tenant_id=tenant_id, limit=normalized_limit)
        ),
        "workbench_refresh_after_matching": _safe_section(
            lambda: _workbench_refresh_after_matching(
                connection,
                tenant_id=tenant_id,
                window_hours=normalized_window_hours,
            )
        ),
        "query_timing_evidence": _safe_section(
            lambda: _query_timing_evidence(connection, limit=normalized_limit)
        ),
        "explain_probes": (
            _safe_section(lambda: _explain_probes(connection))
            if include_explain
            else {"status": "skipped", "reason": "include_explain_false"}
        ),
    }
    available_count = sum(1 for section in sections.values() if section.get("status") == "available")
    missing_fields = _missing_evidence_fields(sections)
    status = "available" if not missing_fields and available_count == len(sections) else "partial"
    return {
        "version": 2,
        "tool": "workbench_compute_evidence",
        "status": status,
        "mode": "read_only",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "window_hours": normalized_window_hours,
        "limit": normalized_limit,
        "admission_status": "blocked_by_missing_real_evidence" if missing_fields else "evidence_collected",
        "production_evidence_required": bool(missing_fields),
        "missing_evidence_fields": missing_fields,
        "sections": sections,
        "forbidden_actions": [
            "database_writes",
            "dirty_scope_claim_or_ack",
            "outbox_enqueue_or_mutation",
            "readiness_mutation",
            "active_generation_publish",
            "go_worker_implementation",
        ],
    }


def _matching_scope_durations(connection: Any, *, tenant_id: str, window_hours: int) -> dict[str, Any]:
    rows = connection.fetch_all(
        """
        select
          status,
          count(*)::bigint as scope_count,
          percentile_disc(0.50) within group (order by duration_ms) filter (where duration_ms is not null)::float as p50_duration_ms,
          percentile_disc(0.95) within group (order by duration_ms) filter (where duration_ms is not null)::float as p95_duration_ms,
          percentile_disc(0.99) within group (order by duration_ms) filter (where duration_ms is not null)::float as p99_duration_ms,
          max(duration_ms)::float as max_duration_ms,
          min(updated_at)::text as first_seen_at,
          max(updated_at)::text as last_seen_at
        from job.workbench_matching_dirty_scopes
        where tenant_id = %s
          and updated_at >= now() - (%s::text || ' hours')::interval
        group by status
        order by status
        """,
        (tenant_id, window_hours),
    )
    by_status = {_text(row.get("status")): _normalize_row(row) for row in rows}
    completed = by_status.get("completed") or by_status.get("done") or {}
    return {
        "by_status": by_status,
        "required_metrics": {
            "worker_scope_duration_p95_ms": completed.get("p95_duration_ms"),
            "worker_scope_duration_p99_ms": completed.get("p99_duration_ms"),
            "completed_sample_count": completed.get("scope_count", 0),
        },
    }


def _matching_scope_samples(connection: Any, *, tenant_id: str, window_hours: int, limit: int) -> list[dict[str, Any]]:
    return [
        _normalize_row(row)
        for row in connection.fetch_all(
            """
            select
              tenant_id,
              to_char(scope_month, 'YYYY-MM') as scope_month,
              status,
              reason,
              attempt_count,
              request_id,
              extract(epoch from now() - available_at)::float as available_age_seconds,
              extract(epoch from now() - coalesce(started_at, available_at))::float as processing_age_seconds,
              started_at::text as started_at,
              completed_at::text as completed_at,
              failed_at::text as failed_at,
              duration_ms,
              source_versions,
              error_summary
            from job.workbench_matching_dirty_scopes
            where tenant_id = %s
              and updated_at >= now() - (%s::text || ' hours')::interval
            order by updated_at desc
            limit %s
            """,
            (tenant_id, window_hours, limit),
        )
    ]


def _worker_heartbeat(connection: Any, *, limit: int) -> dict[str, Any]:
    rows = [
        _normalize_row(row)
        for row in connection.fetch_all(
            """
            select
              worker_id,
              worker_kind,
              status,
              extract(epoch from now() - last_seen_at)::float as heartbeat_lag_seconds,
              last_seen_at::text as last_seen_at,
              payload
            from job.runtime_worker_heartbeats
            where worker_kind = 'workbench-matching'
            order by last_seen_at desc
            limit %s
            """,
            (limit,),
        )
    ]
    latest = rows[0] if rows else None
    return {
        "latest": latest,
        "samples": rows,
        "required_metrics": {
            "heartbeat_lag_seconds": latest.get("heartbeat_lag_seconds") if latest else None,
            "worker_status": latest.get("status") if latest else None,
        },
    }


def _formal_relation_counts(connection: Any, *, tenant_id: str, window_hours: int) -> dict[str, Any]:
    relation_rows = connection.fetch_all(
        """
        select
          coalesce(to_char(month_scope, 'YYYY-MM'), 'unknown') as scope_month,
          count(*)::bigint as relation_count,
          count(*) filter (where status = 'active')::bigint as active_count,
          count(*) filter (where status <> 'active')::bigint as inactive_count,
          sum(cardinality(row_ids))::bigint as member_count
        from app.workbench_pair_relations
        where updated_at >= now() - (%s::text || ' hours')::interval
        group by coalesce(to_char(month_scope, 'YYYY-MM'), 'unknown')
        order by relation_count desc, scope_month
        """,
        (window_hours,),
    )
    return {
        "relations_by_scope": [_normalize_row(row) for row in relation_rows],
        "tenant_id": tenant_id,
    }


def _active_generation_row_counts(connection: Any, *, tenant_id: str, limit: int) -> list[dict[str, Any]]:
    return [
        _normalize_row(row)
        for row in connection.fetch_all(
            """
            select
              gen.scope_key,
              count(*)::bigint as row_count,
              count(*) filter (where gr.source_kind = 'oa')::bigint as oa_row_count,
              count(*) filter (where gr.source_kind = 'bank')::bigint as bank_row_count,
              count(*) filter (where gr.source_kind = 'invoice')::bigint as invoice_row_count,
              count(*) filter (where gr.group_id like 'case:%%')::bigint as active_relation_row_count,
              count(*) filter (where gr.status = 'held' or gr.row_role = 'held')::bigint as held_row_count,
              max(gen.generated_at)::text as generated_at
            from read_model.workbench_generations gen
            join read_model.workbench_group_rows gr
              on gr.generation_id = gen.generation_id
            where gen.tenant_id = %s
              and gen.status = 'active'
            group by gen.scope_key
            order by row_count desc, gen.scope_key
            limit %s
            """,
            (tenant_id, limit),
        )
    ]


def _workbench_refresh_after_matching(connection: Any, *, tenant_id: str, window_hours: int) -> dict[str, Any]:
    row = connection.fetch_one(
        """
        select
          count(*)::bigint as sample_count,
          percentile_disc(0.50) within group (
            order by extract(epoch from (updated_at - created_at)) * 1000
          ) filter (where status = 'done')::float as p50_enqueue_to_done_ms,
          percentile_disc(0.95) within group (
            order by extract(epoch from (updated_at - created_at)) * 1000
          ) filter (where status = 'done')::float as p95_enqueue_to_done_ms,
          percentile_disc(0.99) within group (
            order by extract(epoch from (updated_at - created_at)) * 1000
          ) filter (where status = 'done')::float as p99_enqueue_to_done_ms,
          max(updated_at)::text as last_seen_at
        from job.outbox_events
        where tenant_id = %s
          and event_type = 'workbench.read_model.refresh'
          and updated_at >= now() - (%s::text || ' hours')::interval
          and (
            raw_payload->>'reason' in ('dirty_scope_retry', 'workbench_matching_changed', 'formal_relation_changed')
            or raw_payload->'metadata'->>'source' = 'workbench_matching'
            or raw_payload::text like '%%workbench_matching%%'
          )
        """,
        (tenant_id, window_hours),
    )
    return _normalize_row(row or {})


def _query_timing_evidence(connection: Any, *, limit: int) -> dict[str, Any]:
    try:
        rows = _pg_stat_workbench_queries(connection, limit=limit)
        return {
            "source": "pg_stat_statements",
            "rows": rows,
            "required_metrics": {
                "query_timing_available": bool(rows),
            },
        }
    except Exception as exc:
        return {
            "source": "pg_stat_statements",
            "status": "unavailable",
            "error": str(exc) or exc.__class__.__name__,
            "required_metrics": {
                "query_timing_available": False,
            },
        }


def _pg_stat_workbench_queries(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    return [
        _normalize_row(row)
        for row in connection.fetch_all(
            """
            select
              query,
              calls,
              total_exec_time,
              mean_exec_time,
              rows
            from pg_stat_statements
            where query ilike any(%s)
            order by total_exec_time desc
            limit %s
            """,
            (
                [
                    "%workbench_matching_dirty_scopes%",
                    "%workbench_rows%",
                    "%workbench_generations%",
                    "%workbench_pair_relations%",
                ],
                limit,
            ),
        )
    ]


def _explain_probes(connection: Any) -> list[dict[str, Any]]:
    probes = {
        "matching_dirty_scope_recent": """
            select scope_month, status, duration_ms
            from job.workbench_matching_dirty_scopes
            where tenant_id = 'default'
            order by updated_at desc
            limit 20
        """,
        "active_workbench_generation_row_counts": """
            select gen.scope_key, count(*)::bigint
            from read_model.workbench_generations gen
            join read_model.workbench_group_rows gr
              on gr.generation_id = gen.generation_id
            where gen.tenant_id = 'default'
              and gen.status = 'active'
            group by gen.scope_key
        """,
        "active_formal_relation_counts": """
            select month_scope, count(*)::bigint
            from app.workbench_pair_relations
            where status = 'active'
            group by month_scope
        """,
    }
    rows: list[dict[str, Any]] = []
    for name, sql in probes.items():
        plan = connection.fetch_one(f"explain (format json) {sql}") or {}
        rows.append({"name": name, "plan": plan.get("QUERY PLAN", plan)})
    return rows


def _safe_section(loader: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"status": "available", "data": loader()}
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc) or exc.__class__.__name__}


def _missing_evidence_fields(sections: dict[str, dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    required_sections = {
        "matching_scope_durations": "worker p95/p99 duration by scope",
        "matching_scope_samples": "claimed/processed/failed/stale-completed scope samples",
        "worker_heartbeat": "workbench-matching heartbeat",
        "formal_relation_counts": "formal relation count evidence",
        "active_generation_row_counts": "OA/bank/invoice/active relation row counts",
        "workbench_refresh_after_matching": "Workbench enqueue-to-fresh after matching",
        "query_timing_evidence": "query timing evidence",
    }
    for key, label in required_sections.items():
        section = sections.get(key) or {}
        if section.get("status") != "available":
            missing.append(label)
            continue
        data = section.get("data")
        if not _section_has_required_evidence(key, data):
            missing.append(label)
    return missing


def _section_has_required_evidence(key: str, data: Any) -> bool:
    if data in (None, {}, []):
        return False
    if key == "matching_scope_durations":
        metrics = data.get("required_metrics") if isinstance(data, dict) else {}
        return bool(metrics.get("worker_scope_duration_p95_ms") is not None and metrics.get("worker_scope_duration_p99_ms") is not None)
    if key == "worker_heartbeat":
        metrics = data.get("required_metrics") if isinstance(data, dict) else {}
        return bool(metrics.get("heartbeat_lag_seconds") is not None and metrics.get("worker_status"))
    if key == "formal_relation_counts":
        if not isinstance(data, dict):
            return False
        return bool(data.get("relations_by_scope"))
    if key == "query_timing_evidence":
        metrics = data.get("required_metrics") if isinstance(data, dict) else {}
        return bool(metrics.get("query_timing_available"))
    return True


def _normalize_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {str(key): value for key, value in row.items()}


def _text(value: object) -> str:
    return str(value or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
