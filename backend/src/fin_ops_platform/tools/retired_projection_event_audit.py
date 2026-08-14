from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence, TextIO

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools.cli_reports import (
    postgres_configuration_missing_report,
    write_json_report,
)


DEFAULT_LOOKBACK_HOURS = 24.0
DEFAULT_LIMIT = 2_000
RETIRED_EVENT_PATTERN = "%.read_model.refresh"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail when retired projection refresh events reappear in the durable queue.",
    )
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--since")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        connection = PostgresConnection(PostgresSettings.from_env())
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(
            tool="retired_projection_event_audit",
            message=str(exc),
        )
        write_json_report(report, output=args.output, stdout=stdout)
        return 2
    report = audit_retired_projection_events(
        connection,
        tenant_id=str(args.tenant_id or "default"),
        lookback_hours=max(0.1, float(args.lookback_hours)),
        since=_parse_since(args.since),
        limit=max(1, int(args.limit)),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    return 0 if report["status"] == "pass" else 1


def audit_retired_projection_events(
    connection: Any,
    *,
    tenant_id: str = "default",
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    since: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    rows = (
        recent_retired_projection_events_since(
            connection,
            tenant_id=tenant_id,
            started_at=since,
            limit=limit,
        )
        if since is not None
        else _recent_retired_projection_events(
            connection,
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
            limit=limit,
        )
    )
    return {
        "version": 1,
        "status": "fail" if rows else "pass",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "lookback_hours": lookback_hours,
        "since": since.isoformat() if since is not None else None,
        "retired_projection_event_count": len(rows),
        "error": "forbidden_retired_projection_event_detected" if rows else None,
        "events": [_event_summary(row) for row in rows[:20]],
    }


def recent_retired_projection_events_since(
    connection: Any,
    *,
    tenant_id: str,
    started_at: Any,
    limit: int,
    event_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    event_filter_sql = ""
    event_params: tuple[Any, ...] = ()
    time_filter_sql = "and e.created_at >= %s"
    time_params: tuple[Any, ...] = (started_at,)
    if event_ids is not None:
        exact_event_ids = _exact_event_ids(event_ids)
        event_filter_sql = "and e.id::text = any(%s)"
        event_params = (exact_event_ids,)
        time_filter_sql = ""
        time_params = ()
    rows = connection.fetch_all(
        f"""
        select
          e.id::text as event_id,
          e.event_type,
          e.scope_type,
          e.scope_key,
          e.status as event_status,
          e.created_at,
          e.processed_at,
          e.last_error
        from job.outbox_events e
        where e.tenant_id = %s
          and e.event_type like %s
          {time_filter_sql}
          {event_filter_sql}
        order by e.created_at desc, e.id desc
        limit %s
        """,
        (
            tenant_id,
            RETIRED_EVENT_PATTERN,
            *time_params,
            *event_params,
            max(1, int(limit)),
        ),
    )
    return [dict(row) for row in rows]


def committed_workbench_outbox_event_ids(
    connection: Any,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> list[str]:
    evidence = workbench_idempotency_evidence(
        connection,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )
    if evidence["status"] != "committed":
        raise ValueError("Workbench idempotency record is not committed")
    return list(evidence["outbox_event_ids"])


def workbench_idempotency_evidence(
    connection: Any,
    *,
    tenant_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    normalized_tenant_id = str(tenant_id or "").strip()
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_tenant_id or not normalized_idempotency_key:
        raise ValueError("tenant_id and idempotency_key are required")
    rows = connection.fetch_all(
        """
        select status, outbox_event_ids, response_payload
        from app.workbench_idempotency_records
        where tenant_id = %s
          and idempotency_key = %s
        """,
        (normalized_tenant_id, normalized_idempotency_key),
    )
    if len(rows) != 1:
        raise ValueError("expected exactly one Workbench idempotency record")
    row = rows[0]
    status = str(row.get("status") or "").strip()
    if status not in {"reserved", "committed", "failed"}:
        raise ValueError("Workbench idempotency record has invalid status")
    raw_event_ids = row.get("outbox_event_ids")
    if status == "committed" and not isinstance(raw_event_ids, list):
        raise ValueError("committed Workbench idempotency record has invalid outbox_event_ids")
    event_ids = _exact_event_ids(raw_event_ids) if status == "committed" and raw_event_ids else []
    response_payload = row.get("response_payload")
    if response_payload is None:
        response_payload = {}
    if not isinstance(response_payload, dict):
        raise ValueError("Workbench idempotency record has invalid response_payload")
    return {
        "status": status,
        "outbox_event_ids": event_ids,
        "response_payload": dict(response_payload),
    }


def effective_p99_target_ms_for(target_ms: float, p99_target_ms: float | None) -> float:
    return max(float(p99_target_ms or 0), float(target_ms), 3_000.0)


def _recent_retired_projection_events(
    connection: Any,
    *,
    tenant_id: str,
    lookback_hours: float,
    limit: int,
) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          e.id::text as event_id,
          e.event_type,
          e.scope_type,
          e.scope_key,
          e.status as event_status,
          e.created_at,
          e.processed_at,
          e.last_error
        from job.outbox_events e
        where e.tenant_id = %s
          and e.event_type like %s
          and e.created_at >= now() - (%s * interval '1 hour')
        order by e.created_at desc, e.id desc
        limit %s
        """,
        (tenant_id, RETIRED_EVENT_PATTERN, lookback_hours, max(1, int(limit))),
    )
    return [dict(row) for row in rows]


def _event_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "event_id",
            "event_type",
            "scope_type",
            "scope_key",
            "event_status",
            "created_at",
            "processed_at",
            "last_error",
        )
    }


def _exact_event_ids(values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("outbox_event_ids must be a sequence of strings")
    event_ids = [str(value).strip() if isinstance(value, str) else "" for value in values]
    if not event_ids or any(not event_id for event_id in event_ids):
        raise ValueError("outbox_event_ids must contain non-empty strings")
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("outbox_event_ids must not contain duplicates")
    return event_ids


def _parse_since(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid --since timestamp: {value}") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


if __name__ == "__main__":
    raise SystemExit(main())
