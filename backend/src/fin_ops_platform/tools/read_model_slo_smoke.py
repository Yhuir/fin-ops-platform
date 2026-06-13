from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Sequence, TextIO
from uuid import uuid4
import sys
import re

from fin_ops_platform.services.app_status_read_model_registry import (
    APP_STATUS_READ_MODEL_REGISTRY,
    read_model_by_scope_type,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository


DEFAULT_TARGET_MS = 5_000.0
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.5
MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class SmokeScope:
    read_model_key: str
    scope_type: str
    scope_key: str
    source: str
    row_count: int | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class SmokeEventResult:
    read_model_key: str
    scope_type: str
    scope_key: str
    event_type: str
    event_id: str | None
    status: str
    enqueue_to_fresh_ms: float | None
    handler_duration_ms: float | None
    event_status: str | None
    dirty_status: str | None
    readiness_status: str | None
    source_version: int | None
    error: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a controlled read model enqueue-to-fresh SLO smoke using the existing durable queue.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    parser.add_argument("--output", type=Path, help="Optional path to write the JSON report.")
    parser.add_argument("--apply", action="store_true", help="Actually enqueue and wait. Default is dry-run only.")
    parser.add_argument("--read-model-key", action="append", default=[], help="Limit to one App Status read model key. Repeatable.")
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        metavar="READ_MODEL_KEY=SCOPE_KEY",
        help="Override smoke scope for a read model. Repeatable.",
    )
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--reason", default="read_model_slo_smoke")
    parser.add_argument("--priority", default="high")
    parser.add_argument("--trace-id", default=None)
    parser.add_argument("--target-ms", type=float, default=DEFAULT_TARGET_MS)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    report = run_smoke(
        connection,
        apply=bool(args.apply),
        tenant_id=str(args.tenant_id or "default"),
        read_model_keys=args.read_model_key,
        scope_overrides=_parse_scope_overrides(args.scope),
        reason=str(args.reason or "read_model_slo_smoke"),
        priority=str(args.priority or "high"),
        trace_id=str(args.trace_id or "").strip() or f"read-model-slo-smoke-{uuid4().hex}",
        target_ms=max(1.0, float(args.target_ms)),
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        poll_interval_seconds=max(0.1, float(args.poll_interval_seconds)),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    if report["status"] == "dry_run":
        return 0
    return 0 if report["status"] == "pass" else 1


def run_smoke(
    connection: Any,
    *,
    apply: bool,
    tenant_id: str = "default",
    read_model_keys: Sequence[str] | None = None,
    scope_overrides: dict[str, str] | None = None,
    reason: str = "read_model_slo_smoke",
    priority: str = "high",
    trace_id: str | None = None,
    target_ms: float = DEFAULT_TARGET_MS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    selected_keys = _selected_read_model_keys(read_model_keys)
    scopes = discover_smoke_scopes(
        connection,
        tenant_id=tenant_id,
        read_model_keys=selected_keys,
        scope_overrides=scope_overrides or {},
    )
    missing_keys = [key for key in selected_keys if key not in {scope.read_model_key for scope in scopes}]
    dry_run = not apply
    plan_payload = [asdict(scope) for scope in scopes]
    if dry_run:
        return {
            "version": 1,
            "status": "dry_run",
            "generated_at": datetime.now(UTC).isoformat(),
            "target_ms": target_ms,
            "tenant_id": tenant_id,
            "missing_read_model_keys": missing_keys,
            "planned_scope_count": len(scopes),
            "planned_scopes": plan_payload,
        }

    queue = RuntimeQueueRepository(connection)
    gateway = ReadModelRefreshGateway(queue_repository=queue)
    results: list[SmokeEventResult] = []
    for scope in scopes:
        try:
            events = gateway.enqueue_many_events(
                scope.scope_type,
                [scope.scope_key],
                reason=reason,
                tenant_id=tenant_id,
                priority=priority,
                trace_id=trace_id,
            )
            if not events:
                results.append(
                    SmokeEventResult(
                        read_model_key=scope.read_model_key,
                        scope_type=scope.scope_type,
                        scope_key=scope.scope_key,
                        event_type=f"{scope.scope_type}.read_model.refresh",
                        event_id=None,
                        status="fail",
                        enqueue_to_fresh_ms=None,
                        handler_duration_ms=None,
                        event_status=None,
                        dirty_status=None,
                        readiness_status=None,
                        source_version=None,
                        error="enqueue_returned_no_events",
                    )
                )
                continue
            for event in events:
                definition = read_model_by_scope_type().get(str(event.scope_type))
                read_model_key = definition.key if definition is not None else scope.read_model_key
                results.append(
                    wait_for_event_fresh(
                        connection,
                        event_id=str(event.event_id),
                        read_model_key=read_model_key,
                        scope_type=str(event.scope_type),
                        scope_key=str(event.scope_key),
                        tenant_id=tenant_id,
                        target_ms=target_ms,
                        timeout_seconds=timeout_seconds,
                        poll_interval_seconds=poll_interval_seconds,
                    )
                )
        except Exception as exc:
            results.append(
                SmokeEventResult(
                    read_model_key=scope.read_model_key,
                    scope_type=scope.scope_type,
                    scope_key=scope.scope_key,
                    event_type=f"{scope.scope_type}.read_model.refresh",
                    event_id=None,
                    status="fail",
                    enqueue_to_fresh_ms=None,
                    handler_duration_ms=None,
                    event_status=None,
                    dirty_status=None,
                    readiness_status=None,
                    source_version=None,
                    error=str(exc) or exc.__class__.__name__,
                )
            )
    failed = [result for result in results if result.status != "pass"]
    return {
        "version": 1,
        "status": "pass" if not failed and not missing_keys else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "target_ms": target_ms,
        "tenant_id": tenant_id,
        "missing_read_model_keys": missing_keys,
        "planned_scope_count": len(scopes),
        "planned_scopes": plan_payload,
        "result_count": len(results),
        "failed_count": len(failed) + len(missing_keys),
        "results": [asdict(result) for result in results],
    }


def discover_smoke_scopes(
    connection: Any,
    *,
    tenant_id: str = "default",
    read_model_keys: Sequence[str] | None = None,
    scope_overrides: dict[str, str] | None = None,
) -> list[SmokeScope]:
    selected_keys = _selected_read_model_keys(read_model_keys)
    overrides = scope_overrides or {}
    readiness = _fresh_readiness_by_key(connection, tenant_id=tenant_id)
    workbench_generations = _active_workbench_generations(connection, tenant_id=tenant_id)
    scopes: list[SmokeScope] = []
    for key in selected_keys:
        definition = APP_STATUS_READ_MODEL_REGISTRY[key]
        if key in overrides:
            scopes.append(
                SmokeScope(
                    read_model_key=key,
                    scope_type=definition.scope_type,
                    scope_key=overrides[key],
                    source="override",
                )
            )
            continue
        if key == "workbench":
            chosen = _choose_direct_scope(workbench_generations) or _choose_direct_scope(readiness.get(key, []))
        else:
            chosen = _choose_direct_scope(readiness.get(key, []))
        if chosen is None:
            continue
        scopes.append(
            SmokeScope(
                read_model_key=key,
                scope_type=definition.scope_type,
                scope_key=str(chosen.get("scope_key") or ""),
                source=str(chosen.get("_source") or "readiness"),
                row_count=_optional_int(chosen.get("row_count")),
                updated_at=str(chosen.get("updated_at") or "") or None,
            )
        )
    return scopes


def wait_for_event_fresh(
    connection: Any,
    *,
    event_id: str,
    read_model_key: str,
    scope_type: str,
    scope_key: str,
    tenant_id: str,
    target_ms: float,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> SmokeEventResult:
    deadline = monotonic() + max(1.0, timeout_seconds)
    last_error = None
    while True:
        event = _event_status(connection, event_id)
        readiness = _readiness_status(
            connection,
            tenant_id=tenant_id,
            read_model_key=read_model_key,
            scope_type=scope_type,
            scope_key=scope_key,
        )
        dirty = _dirty_scope_status(connection, tenant_id=str((event or {}).get("tenant_id") or "default"), scope_type=scope_type, scope_key=scope_key)
        event_status = str((event or {}).get("status") or "").strip() or None
        readiness_status = str((readiness or {}).get("status") or "").strip() or None
        dirty_status = str((dirty or {}).get("status") or "").strip() or None
        source_version = _optional_int((event or {}).get("source_version"))
        enqueue_ms = _duration_ms((event or {}).get("created_at"), (event or {}).get("processed_at"))
        handler_ms = _runtime_handler_duration_ms(event)
        if event_status == "done" and readiness_status == "fresh":
            status = "pass" if enqueue_ms is not None and enqueue_ms <= target_ms else "fail"
            return SmokeEventResult(
                read_model_key=read_model_key,
                scope_type=scope_type,
                scope_key=scope_key,
                event_type=str((event or {}).get("event_type") or f"{scope_type}.read_model.refresh"),
                event_id=event_id,
                status=status,
                enqueue_to_fresh_ms=enqueue_ms,
                handler_duration_ms=handler_ms,
                event_status=event_status,
                dirty_status=dirty_status,
                readiness_status=readiness_status,
                source_version=source_version,
                error=None if status == "pass" else f"enqueue_to_fresh_ms_exceeded_target:{enqueue_ms}>{target_ms}",
            )
        if event_status in {"failed", "dead_lettered"} or readiness_status in {"failed", "unavailable", "schema_mismatch", "source_mismatch"}:
            last_error = str((event or {}).get("last_error") or (readiness or {}).get("last_error") or event_status or readiness_status)
            return SmokeEventResult(
                read_model_key=read_model_key,
                scope_type=scope_type,
                scope_key=scope_key,
                event_type=str((event or {}).get("event_type") or f"{scope_type}.read_model.refresh"),
                event_id=event_id,
                status="fail",
                enqueue_to_fresh_ms=enqueue_ms,
                handler_duration_ms=handler_ms,
                event_status=event_status,
                dirty_status=dirty_status,
                readiness_status=readiness_status,
                source_version=source_version,
                error=last_error,
            )
        if monotonic() >= deadline:
            return SmokeEventResult(
                read_model_key=read_model_key,
                scope_type=scope_type,
                scope_key=scope_key,
                event_type=str((event or {}).get("event_type") or f"{scope_type}.read_model.refresh"),
                event_id=event_id,
                status="timeout",
                enqueue_to_fresh_ms=enqueue_ms,
                handler_duration_ms=handler_ms,
                event_status=event_status,
                dirty_status=dirty_status,
                readiness_status=readiness_status,
                source_version=source_version,
                error=last_error or "timeout_waiting_for_done_and_fresh",
            )
        sleep(max(0.1, poll_interval_seconds))


def _fresh_readiness_by_key(connection: Any, *, tenant_id: str) -> dict[str, list[dict[str, Any]]]:
    rows = connection.fetch_all(
        """
        select read_model_key, scope_type, scope_key, status, row_count, updated_at::text as updated_at
        from read_model.app_status_readiness
        where tenant_id = %s
          and status = 'fresh'
        order by read_model_key, updated_at desc
        """,
        (tenant_id,),
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        payload = dict(row)
        payload["_source"] = "readiness"
        key = str(payload.get("read_model_key") or "").strip()
        if key:
            grouped.setdefault(key, []).append(payload)
    return grouped


def _active_workbench_generations(connection: Any, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select scope_key, row_count, updated_at::text as updated_at
        from read_model.workbench_generations
        where tenant_id = %s
          and status = 'active'
        order by updated_at desc
        """,
        (tenant_id,),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["_source"] = "active_generation"
        result.append(payload)
    return result


def _choose_direct_scope(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    non_parent = [row for row in rows if not _looks_like_parent_scope(row.get("scope_key"))]
    non_empty = [row for row in non_parent if (_optional_int(row.get("row_count")) or 0) > 0]
    if non_empty:
        return non_empty[0]
    if non_parent:
        return non_parent[0]
    return rows[0] if rows else None


def _looks_like_parent_scope(scope_key: Any) -> bool:
    text = str(scope_key or "").strip()
    if not text:
        return True
    if text in {"all", "active:all", "all:all"}:
        return True
    parts = text.split(":")
    if len(parts) == 2:
        return not bool(MONTH_SCOPE_RE.match(parts[1]))
    return False


def _event_status(connection: Any, event_id: str) -> dict[str, Any] | None:
    return connection.fetch_one(
        """
        select
          id::text as event_id,
          tenant_id,
          event_type,
          scope_type,
          scope_key,
          status,
          source_version,
          created_at,
          processed_at,
          updated_at,
          last_error,
          raw_payload
        from job.outbox_events
        where id = %s
        """,
        (event_id,),
    )


def _readiness_status(connection: Any, *, tenant_id: str, read_model_key: str, scope_type: str, scope_key: str) -> dict[str, Any] | None:
    return connection.fetch_one(
        """
        select status, updated_at, last_error, row_count, source_versions
        from read_model.app_status_readiness
        where tenant_id = %s
          and read_model_key = %s
          and scope_type = %s
          and scope_key = %s
        """,
        (tenant_id, read_model_key, scope_type, scope_key),
    )


def _dirty_scope_status(connection: Any, *, tenant_id: str, scope_type: str, scope_key: str) -> dict[str, Any] | None:
    return connection.fetch_one(
        """
        select status, source_version, updated_at, last_error
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type = %s
          and scope_key = %s
        """,
        (tenant_id, scope_type, scope_key),
    )


def _runtime_handler_duration_ms(event: dict[str, Any] | None) -> float | None:
    raw = (event or {}).get("raw_payload")
    if not isinstance(raw, dict):
        return None
    runtime_result = raw.get("runtime_result")
    if not isinstance(runtime_result, dict):
        return None
    for key in ("duration_ms", "handler_duration_ms"):
        value = _optional_float(runtime_result.get(key))
        if value is not None:
            return round(value, 3)
    return None


def _duration_ms(start: Any, end: Any) -> float | None:
    started = _coerce_datetime(start)
    ended = _coerce_datetime(end)
    if started is None or ended is None:
        return None
    return round(max(0.0, (ended - started).total_seconds() * 1000), 3)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if not value:
        return None
    text = str(value).strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_scope_overrides(values: Sequence[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in str(value):
            raise SystemExit(f"--scope must use READ_MODEL_KEY=SCOPE_KEY, got {value!r}")
        key, scope_key = str(value).split("=", 1)
        normalized_key = key.strip()
        normalized_scope_key = scope_key.strip()
        if normalized_key not in APP_STATUS_READ_MODEL_REGISTRY:
            raise SystemExit(f"Unknown read model key in --scope: {normalized_key!r}")
        if not normalized_scope_key:
            raise SystemExit(f"Empty scope key in --scope for {normalized_key!r}")
        overrides[normalized_key] = normalized_scope_key
    return overrides


def _selected_read_model_keys(read_model_keys: Sequence[str] | None) -> list[str]:
    raw_keys = [str(key or "").strip() for key in (read_model_keys or []) if str(key or "").strip()]
    if not raw_keys:
        return list(APP_STATUS_READ_MODEL_REGISTRY.keys())
    unknown = [key for key in raw_keys if key not in APP_STATUS_READ_MODEL_REGISTRY]
    if unknown:
        raise ValueError(f"Unknown read model keys: {', '.join(unknown)}")
    return raw_keys


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
