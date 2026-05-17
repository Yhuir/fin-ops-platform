#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


JOIN_SOURCES = (
    "app.data_reset_requests",
    "job.worker_tasks",
    "job.outbox_events",
    "audit.events",
    "app.write_idempotency_records",
    "job.worker_attempts",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Output data reset lineage evidence joined across request, worker, outbox, audit, idempotency and attempt facts."
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--data-reset-request-id")
    parser.add_argument("--task-id")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_lineage_report(args)
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] != "ERROR" else 2


def build_lineage_report(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    base: dict[str, Any] = {
        "report": "data-reset-audit-lineage",
        "generated_at": generated_at,
        "status": "NO_GO_LINEAGE_DATABASE_REQUIRED",
        "join_sources": list(JOIN_SOURCES),
        "filters": {
            "data_reset_request_id": args.data_reset_request_id,
            "task_id": args.task_id,
            "limit": max(1, int(args.limit or 20)),
        },
        "rows": [],
        "gaps": [],
    }
    if not args.database_url:
        base["gaps"].append(
            {
                "source": "postgres",
                "status": "missing",
                "detail": "DATABASE_URL or --database-url is required to query lineage facts.",
            }
        )
        return base

    try:
        import psycopg  # type: ignore[import-not-found]
        from psycopg.rows import dict_row  # type: ignore[import-not-found]
    except ImportError as exc:
        base["status"] = "ERROR"
        base["gaps"].append(
            {
                "source": "python_dependency",
                "status": "missing",
                "detail": "psycopg is required to query PostgreSQL lineage facts.",
                "error": str(exc),
            }
        )
        return base

    try:
        with psycopg.connect(args.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_lineage_sql(args), _lineage_params(args))
                rows = [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        base["status"] = "ERROR"
        base["gaps"].append(
            {
                "source": "postgres",
                "status": "query_failed",
                "detail": str(exc),
            }
        )
        return base

    base["rows"] = [_row_report(row) for row in rows]
    base["gaps"] = _report_gaps(base["rows"])
    base["status"] = "GO" if rows and not base["gaps"] else "NO_GO_LINEAGE_GAPS_REMAIN"
    return base


def _lineage_sql(args: argparse.Namespace) -> str:
    filters = []
    if args.data_reset_request_id:
        filters.append("d.id = %s::uuid")
    if args.task_id:
        filters.append("d.worker_task_id = %s::uuid")
    where_clause = "where " + " and ".join(filters) if filters else ""
    return f"""
    select
      d.id::text as data_reset_request_id,
      d.action,
      d.status as data_reset_status,
      d.approval_id,
      d.backup_evidence_id,
      d.scope,
      d.worker_task_id::text,
      d.outbox_event_id::text,
      d.execution_mode,
      d.requested_by,
      d.requested_at,
      d.completed_at,
      d.failed_at,
      d.failure_code,
      d.failure_message,
      d.idempotency_key,
      t.status as worker_task_status,
      t.phase as worker_task_phase,
      t.result_summary as worker_result_summary,
      t.error_code as worker_error_code,
      t.error_summary as worker_error_summary,
      o.status as outbox_status,
      o.subject as outbox_subject,
      o.event_type as outbox_event_type,
      o.trace_id as outbox_trace_id,
      a.id::text as audit_event_id,
      a.event_type as audit_event_type,
      a.trace_id as audit_trace_id,
      i.operation as idempotency_operation,
      i.status as idempotency_status,
      attempts.attempts as worker_attempts
    from app.data_reset_requests d
    left join job.worker_tasks t on t.id = d.worker_task_id
    left join job.outbox_events o on o.id = d.outbox_event_id
    left join audit.events a
      on a.id = d.audit_event_id
      or (
        a.entity_type = 'data_reset_request'
        and a.entity_id = d.id
      )
    left join app.write_idempotency_records i
      on i.operation = 'data_reset.request'
      and i.idempotency_key = d.idempotency_key
    left join lateral (
      select coalesce(
        jsonb_agg(
          jsonb_build_object(
            'attempt_id', wa.id::text,
            'attempt_no', wa.attempt_no,
            'worker_id', wa.worker_id,
            'status', wa.status,
            'started_at', wa.started_at,
            'finished_at', wa.finished_at,
            'error_code', wa.error_code,
            'error_summary', wa.error_summary
          )
          order by wa.attempt_no
        ),
        '[]'::jsonb
      ) as attempts
      from job.worker_attempts wa
      where wa.task_id = d.worker_task_id
    ) attempts on true
    {where_clause}
    order by d.requested_at desc
    limit %s
    """


def _lineage_params(args: argparse.Namespace) -> tuple[object, ...]:
    params: list[object] = []
    if args.data_reset_request_id:
        params.append(args.data_reset_request_id)
    if args.task_id:
        params.append(args.task_id)
    params.append(max(1, int(args.limit or 20)))
    return tuple(params)


def _row_report(row: dict[str, Any]) -> dict[str, Any]:
    attempts = row.get("worker_attempts") or []
    return {
        "data_reset_request": {
            "id": row.get("data_reset_request_id"),
            "action": row.get("action"),
            "status": row.get("data_reset_status"),
            "approval_id": row.get("approval_id"),
            "backup_evidence_id": row.get("backup_evidence_id"),
            "scope": row.get("scope"),
            "worker_task_id": row.get("worker_task_id"),
            "outbox_event_id": row.get("outbox_event_id"),
            "execution_mode": row.get("execution_mode"),
            "requested_by": row.get("requested_by"),
            "requested_at": row.get("requested_at"),
            "completed_at": row.get("completed_at"),
            "failed_at": row.get("failed_at"),
            "failure_code": row.get("failure_code"),
            "failure_message": row.get("failure_message"),
            "idempotency_key": row.get("idempotency_key"),
        },
        "worker_task": {
            "status": row.get("worker_task_status"),
            "phase": row.get("worker_task_phase"),
            "result_summary": row.get("worker_result_summary"),
            "error_code": row.get("worker_error_code"),
            "error_summary": row.get("worker_error_summary"),
        },
        "outbox_event": {
            "status": row.get("outbox_status"),
            "subject": row.get("outbox_subject"),
            "event_type": row.get("outbox_event_type"),
            "trace_id": row.get("outbox_trace_id"),
        },
        "audit_event": {
            "id": row.get("audit_event_id"),
            "event_type": row.get("audit_event_type"),
            "trace_id": row.get("audit_trace_id"),
        },
        "idempotency_record": {
            "operation": row.get("idempotency_operation"),
            "status": row.get("idempotency_status"),
        },
        "worker_attempts": attempts,
        "join_evidence": {
            "app.data_reset_requests": True,
            "job.worker_tasks": bool(row.get("worker_task_status")),
            "job.outbox_events": bool(row.get("outbox_status")),
            "audit.events": bool(row.get("audit_event_id")),
            "app.write_idempotency_records": bool(row.get("idempotency_operation")),
            "job.worker_attempts": bool(attempts),
        },
    }


def _report_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return [{"source": "app.data_reset_requests", "status": "missing", "detail": "No data reset request rows matched the filters."}]
    gaps: list[dict[str, Any]] = []
    for row in rows:
        request_id = row["data_reset_request"]["id"]
        for source, present in row["join_evidence"].items():
            if not present:
                gaps.append(
                    {
                        "data_reset_request_id": request_id,
                        "source": source,
                        "status": "missing",
                        "detail": f"{source} did not join for this data reset request.",
                    }
                )
    return gaps


if __name__ == "__main__":
    raise SystemExit(main())
