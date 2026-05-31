from __future__ import annotations

from typing import Any

from fin_ops_platform.services.rabbitmq_runtime import rabbitmq_event_routes
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueSettings
from fin_ops_platform.services.runtime_worker_registry import (
    read_model_event_types,
    registration_by_worker_kind,
    worker_registrations,
)


READ_MODEL_EVENT_TYPES: dict[str, tuple[str, str]] = read_model_event_types()

EMPTY_PERCENTILES = {"p50": None, "p95": None, "p99": None}


class RuntimeMonitoringRepository:
    def __init__(self, connection: Any, rabbitmq_metrics_provider: Any | None = None) -> None:
        self._connection = connection
        self._rabbitmq_metrics_provider = rabbitmq_metrics_provider

    def health_summary(self, *, stale_after_seconds: int = 300) -> dict[str, Any]:
        queue_rows = self._connection.fetch_all(
            """
            select status, count(*)::bigint as count
            from job.outbox_events
            group by status
            order by status
            """
        )
        age_row = self._connection.fetch_one(
            """
            select extract(epoch from max(now() - created_at))::float as max_pending_age_seconds
            from job.outbox_events
            where status = 'pending'
            """
        )
        dirty_count_rows = self._connection.fetch_all(
            """
            select status, count(*)::bigint as count
            from job.read_model_dirty_scopes
            group by status
            order by status
            """
        )
        stale_rows = self._connection.fetch_all(
            """
            select
              tenant_id,
              scope_type,
              scope_key,
              status,
              extract(epoch from now() - updated_at)::float as age_seconds,
              attempts,
              last_error
            from job.read_model_dirty_scopes
            where status in ('pending', 'processing', 'failed')
              and updated_at < now() - (%s * interval '1 second')
            order by updated_at, tenant_id, scope_type, scope_key
            limit 20
            """,
            (stale_after_seconds,),
        )
        worker_lag_row = self._connection.fetch_one(
            """
            with latest_worker_kind_heartbeats as (
              select distinct on (worker_kind)
                worker_kind,
                last_seen_at
              from job.runtime_worker_heartbeats
              order by worker_kind, last_seen_at desc
            )
            select extract(epoch from max(now() - last_seen_at))::float as max_worker_heartbeat_lag_seconds
            from latest_worker_kind_heartbeats
            where worker_kind <> 'runtime'
            """
        )
        refresh_duration_row = self._connection.fetch_one(
            """
            select
              percentile_cont(0.5) within group (
                order by ((raw_payload->'runtime_result'->>'duration_ms')::numeric)
              )::float as p50_ms,
              percentile_cont(0.95) within group (
                order by ((raw_payload->'runtime_result'->>'duration_ms')::numeric)
              )::float as p95_ms,
              percentile_cont(0.99) within group (
                order by ((raw_payload->'runtime_result'->>'duration_ms')::numeric)
              )::float as p99_ms
            from job.outbox_events
            where event_type like '%%.read_model.refresh'
              and status = 'done'
              and raw_payload->'runtime_result' ? 'duration_ms'
            """
        )
        refresh_failure_row = self._connection.fetch_one(
            """
            select
              count(*) filter (where status in ('failed', 'dead_lettered'))::bigint as failed_count,
              count(*)::bigint as read_model_refresh_total
            from job.outbox_events
            where event_type like '%%.read_model.refresh'
            """
        )
        publish_rows = self._connection.fetch_all(
            """
            select publish_status, count(*)::bigint as count
            from job.outbox_events
            where status = 'pending'
              and event_type = any(%s)
            group by publish_status
            order by publish_status
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_lag_row = self._connection.fetch_one(
            """
            select extract(epoch from max(now() - created_at))::float as max_unpublished_age_seconds
            from job.outbox_events
            where status = 'pending'
              and event_type = any(%s)
              and publish_status in ('unpublished', 'failed')
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_confirm_latency_row = self._connection.fetch_one(
            """
            select
              percentile_cont(0.5) within group (
                order by ((raw_payload->'rabbitmq_publish'->>'confirm_latency_ms')::numeric)
              )::float as p50_ms,
              percentile_cont(0.95) within group (
                order by ((raw_payload->'rabbitmq_publish'->>'confirm_latency_ms')::numeric)
              )::float as p95_ms,
              percentile_cont(0.99) within group (
                order by ((raw_payload->'rabbitmq_publish'->>'confirm_latency_ms')::numeric)
              )::float as p99_ms
            from job.outbox_events
            where publish_status = 'published'
              and raw_payload->'rabbitmq_publish' ? 'confirm_latency_ms'
            """
        )
        pending_outbox_by_scope = self._pending_outbox_events_by_scope()
        dirty_scopes_by_scope = self._dirty_scopes_by_scope()
        workbench_read_model = self._workbench_read_model_summary()
        queue_backlog = {str(row["status"]): int(row["count"]) for row in queue_rows}
        dirty_scopes = {str(row["status"]): int(row["count"]) for row in dirty_count_rows}
        publish_status = {str(row["publish_status"]): int(row["count"]) for row in publish_rows}
        stale_dirty_scopes = [
            {
                "tenant_id": row.get("tenant_id"),
                "scope_type": row.get("scope_type"),
                "scope_key": row.get("scope_key"),
                "status": row.get("status"),
                "age_seconds": row.get("age_seconds"),
                "attempts": row.get("attempts"),
                "last_error": row.get("last_error"),
            }
            for row in stale_rows
        ]
        max_pending_age_seconds = (age_row or {}).get("max_pending_age_seconds")
        total_refresh_count = int((refresh_failure_row or {}).get("read_model_refresh_total") or 0)
        failed_refresh_count = int((refresh_failure_row or {}).get("failed_count") or 0)
        rabbitmq_metrics = self._rabbitmq_metrics()
        worker_metrics = self.dashboard_worker_metrics()
        missing_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "required_worker_missing")
        stale_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "worker_heartbeat_stale")
        return {
            "queue_backlog": queue_backlog,
            "dirty_scopes": dirty_scopes,
            "failed_jobs": int(queue_backlog.get("failed", 0)) + int(queue_backlog.get("dead_lettered", 0)),
            "max_pending_age_seconds": max_pending_age_seconds,
            "oldest_pending_event_age_seconds": max_pending_age_seconds,
            "worker_heartbeat_lag_seconds": (worker_lag_row or {}).get("max_worker_heartbeat_lag_seconds"),
            "worker_metrics": worker_metrics,
            "missing_required_worker_count": missing_required_worker_count,
            "stale_required_worker_count": stale_required_worker_count,
            "read_model_refresh_duration_ms": {
                "p50": (refresh_duration_row or {}).get("p50_ms"),
                "p95": (refresh_duration_row or {}).get("p95_ms"),
                "p99": (refresh_duration_row or {}).get("p99_ms"),
            },
            "read_model_refresh_failure_rate": (
                round(failed_refresh_count / total_refresh_count, 6) if total_refresh_count else 0.0
            ),
            "rabbitmq_publish_status": publish_status,
            "rabbitmq_unpublished_backlog": int(publish_status.get("unpublished", 0)),
            "rabbitmq_publish_failed_backlog": int(publish_status.get("failed", 0)),
            "rabbitmq_dispatcher_lag_seconds": (publish_lag_row or {}).get("max_unpublished_age_seconds"),
            "rabbitmq_publish_confirm_latency_ms": {
                "p50": (publish_confirm_latency_row or {}).get("p50_ms"),
                "p95": (publish_confirm_latency_row or {}).get("p95_ms"),
                "p99": (publish_confirm_latency_row or {}).get("p99_ms"),
            },
            "rabbitmq_dispatch_event_types": list(_rabbitmq_dispatch_event_types()),
            **rabbitmq_metrics,
            "stale_dirty_scope_count": len(stale_dirty_scopes),
            "stale_dirty_scopes": stale_dirty_scopes,
            "pending_outbox_events_by_scope": pending_outbox_by_scope,
            "dirty_scopes_by_scope": dirty_scopes_by_scope,
            "workbench_read_model": workbench_read_model,
        }

    def _pending_outbox_events_by_scope(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            with pending_outbox_by_scope as (
              select
                event_type,
                status,
                coalesce(scope_type, raw_payload->>'scope_type', aggregate_type, '') as scope_type,
                coalesce(scope_key, raw_payload->>'scope_key', aggregate_id, '') as scope_key,
                count(*)::bigint as count,
                extract(epoch from max(now() - created_at))::float as oldest_age_seconds,
                max(attempts)::integer as attempts,
                max(coalesce(last_error, '')) as last_error
              from job.outbox_events
              where status in ('pending', 'processing', 'failed', 'dead_lettered')
              group by 1, 2, 3, 4
              order by oldest_age_seconds desc nulls last, event_type, scope_type, scope_key
              limit 30
            )
            select * from pending_outbox_by_scope
            """
        )
        return [
            {
                "event_type": str(row.get("event_type") or ""),
                "status": str(row.get("status") or ""),
                "scope_type": str(row.get("scope_type") or ""),
                "scope_key": str(row.get("scope_key") or ""),
                "count": int(row.get("count") or 0),
                "oldest_age_seconds": row.get("oldest_age_seconds"),
                "attempts": int(row.get("attempts") or 0),
                "last_error": str(row.get("last_error") or ""),
            }
            for row in rows
        ]

    def _dirty_scopes_by_scope(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            with dirty_scope_backlog_by_scope as (
              select
                scope_type,
                scope_key,
                status,
                count(*)::bigint as count,
                extract(epoch from max(now() - updated_at))::float as oldest_age_seconds,
                max(attempts)::integer as attempts,
                max(coalesce(last_error, '')) as last_error
              from job.read_model_dirty_scopes
              where status in ('pending', 'processing', 'failed')
              group by scope_type, scope_key, status
              order by oldest_age_seconds desc nulls last, scope_type, scope_key
              limit 30
            )
            select * from dirty_scope_backlog_by_scope
            """
        )
        return [
            {
                "scope_type": str(row.get("scope_type") or ""),
                "scope_key": str(row.get("scope_key") or ""),
                "status": str(row.get("status") or ""),
                "count": int(row.get("count") or 0),
                "oldest_age_seconds": row.get("oldest_age_seconds"),
                "attempts": int(row.get("attempts") or 0),
                "last_error": str(row.get("last_error") or ""),
            }
            for row in rows
        ]

    def _workbench_read_model_summary(self) -> dict[str, Any]:
        generation_rows = self._connection.fetch_all(
            """
            with workbench_generation_status_counts as (
              select status, count(*)::bigint as count
              from read_model.workbench_generations
              where tenant_id = 'default'
                and status in ('active', 'building', 'failed')
              group by status
              order by status
            )
            select * from workbench_generation_status_counts
            """
        )
        active_rows = self._connection.fetch_all(
            """
            with workbench_active_generation_totals as (
              select
                count(*)::bigint as active_scope_count,
                coalesce(sum(row_count), 0)::bigint as active_row_count,
                coalesce(sum(group_count), 0)::bigint as active_group_count,
                coalesce(sum(summary_count), 0)::bigint as active_summary_count,
                max(activated_at)::text as latest_generated_at
              from read_model.workbench_generations
              where tenant_id = 'default'
                and status = 'active'
            )
            select * from workbench_active_generation_totals
            """
        )
        all_scope_row = self._connection.fetch_one(
            """
            select
              status,
              row_count,
              group_count,
              summary_count,
              updated_at::text as updated_at,
              coalesce(last_error, '') as last_error
            from read_model.workbench_generations workbench_all_scope_generation
            where tenant_id = 'default'
              and scope_key = 'all'
              and status in ('active', 'building', 'failed')
            order by
              case status when 'active' then 0 when 'building' then 1 else 2 end,
              updated_at desc
            limit 1
            """
        )
        status_counts = {str(row.get("status") or ""): int(row.get("count") or 0) for row in generation_rows}
        active_totals = active_rows[0] if active_rows else {}
        return {
            "generation_status_counts": status_counts,
            "active_scope_count": int(active_totals.get("active_scope_count") or 0),
            "active_row_count": int(active_totals.get("active_row_count") or 0),
            "active_group_count": int(active_totals.get("active_group_count") or 0),
            "active_summary_count": int(active_totals.get("active_summary_count") or 0),
            "building_scope_count": int(status_counts.get("building", 0)),
            "failed_scope_count": int(status_counts.get("failed", 0)),
            "latest_generated_at": active_totals.get("latest_generated_at"),
            "all_scope": {
                "status": str((all_scope_row or {}).get("status") or ""),
                "row_count": int((all_scope_row or {}).get("row_count") or 0),
                "group_count": int((all_scope_row or {}).get("group_count") or 0),
                "summary_count": int((all_scope_row or {}).get("summary_count") or 0),
                "updated_at": (all_scope_row or {}).get("updated_at"),
                "last_error": str((all_scope_row or {}).get("last_error") or ""),
            },
        }

    def _rabbitmq_metrics(self) -> dict[str, Any]:
        provider = self._rabbitmq_metrics_provider
        if provider is None:
            try:
                from fin_ops_platform.services.rabbitmq_runtime import RabbitMqManagementMetrics
                from fin_ops_platform.services.runtime_queue import RuntimeQueueSettings

                provider = RabbitMqManagementMetrics(RuntimeQueueSettings.from_env())
            except Exception as exc:
                return {"rabbitmq_metric_error": str(exc) or exc.__class__.__name__}
        summary = provider.summary()
        return summary if isinstance(summary, dict) else {}

    def dashboard_outbox_metric(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select
              count(*) filter (where status = 'pending')::bigint as pending_count,
              count(*) filter (where publish_status = 'publishing')::bigint as publishing_count,
              count(*) filter (where status in ('failed', 'dead_lettered'))::bigint as failed_count,
              count(*) filter (where publish_status = 'failed')::bigint as publish_failed_count,
              extract(epoch from max(now() - created_at) filter (where status = 'pending'))::float as oldest_pending_age_seconds
            from job.outbox_events
            """
        ) or {}
        return {
            "pending_count": _optional_int(row.get("pending_count")),
            "publishing_count": _optional_int(row.get("publishing_count")),
            "failed_count": _optional_int(row.get("failed_count")),
            "publish_failed_count": _optional_int(row.get("publish_failed_count")),
            "oldest_pending_age_seconds": _optional_float(row.get("oldest_pending_age_seconds")),
            "status": "available",
        }

    def dashboard_queue_metrics(self) -> list[dict[str, Any]]:
        settings = RuntimeQueueSettings.from_env()
        routes = rabbitmq_event_routes(settings)
        summary = self._rabbitmq_metrics()
        queues = summary.get("rabbitmq_queues") if isinstance(summary, dict) else None
        metric_error = summary.get("rabbitmq_metric_error") if isinstance(summary, dict) else None
        metrics_available = isinstance(queues, dict) and not metric_error
        rows: list[dict[str, Any]] = []
        for event_type, route in routes.items():
            queue_metric = queues.get(event_type) if metrics_available else None
            queue_payload = queue_metric if isinstance(queue_metric, dict) else {}
            if metrics_available:
                rows.append(
                    {
                        "event_type": event_type,
                        "queue": route.queue,
                        "messages": _optional_int(queue_payload.get("messages")),
                        "unacked": _optional_int(queue_payload.get("unacked")),
                        "consumers": _optional_int(queue_payload.get("consumers")),
                        "dlq_messages": _optional_int(queue_payload.get("dead_letter_messages")),
                        "status": "available",
                    }
                )
            else:
                rows.append(
                    {
                        "event_type": event_type,
                        "queue": route.queue,
                        "messages": None,
                        "unacked": None,
                        "consumers": None,
                        "dlq_messages": None,
                        "status": "unknown",
                        "warning_code": "rabbitmq_metrics_unavailable",
                    }
                )
        return rows

    def dashboard_read_model_metrics(self) -> list[dict[str, Any]]:
        event_types = tuple(READ_MODEL_EVENT_TYPES.keys())
        duration_rows = self._connection.fetch_all(
            """
            with refresh_events as (
              select
                event_type,
                updated_at,
                case
                  when coalesce(aggregate_id, raw_payload->>'scope_key', raw_payload->'runtime_result'->>'scope_key', '') = 'all'
                    then 'full'
                  when coalesce(raw_payload->>'scope_key', raw_payload->'runtime_result'->>'scope_key', '') ~ '^\\d{4}-\\d{2}$'
                    then 'incremental'
                  else 'unknown'
                end as refresh_kind,
                ((raw_payload->'runtime_result'->>'duration_ms')::numeric) as duration_ms
              from job.outbox_events
              where event_type = any(%s)
                and status = 'done'
                and raw_payload->'runtime_result' ? 'duration_ms'
            ),
            metric_windows(window_name, started_at) as (
              values
                ('recent_15m', now() - interval '15 minutes'),
                ('recent_1h', now() - interval '1 hour'),
                ('all_time', '-infinity'::timestamptz)
            )
            select
              event_type,
              window_name,
              refresh_kind,
              count(*)::bigint as sample_count,
              max(updated_at)::text as last_completed_at,
              percentile_cont(0.5) within group (
                order by duration_ms
              )::float as p50_ms,
              percentile_cont(0.95) within group (
                order by duration_ms
              )::float as p95_ms,
              percentile_cont(0.99) within group (
                order by duration_ms
              )::float as p99_ms
            from refresh_events
            join metric_windows on refresh_events.updated_at >= metric_windows.started_at
            group by event_type, window_name, refresh_kind
            """,
            (list(event_types),),
        )
        dirty_rows = self._connection.fetch_all(
            """
            select
              scope_type,
              count(*) filter (where status in ('pending', 'processing', 'failed'))::bigint as stale_count,
              count(*) filter (where status = 'failed')::bigint as unavailable_count
            from job.read_model_dirty_scopes
            where scope_type = any(%s)
            group by scope_type
            """,
            (list({scope_type for _, scope_type in READ_MODEL_EVENT_TYPES.values()}),),
        )
        workbench_consistency_unavailable_count = 0
        workbench_consistency_warning: str | None = None
        try:
            consistency_row = self._connection.fetch_one(
                """
                select count(*)::bigint as inconsistent_count
                from read_model.workbench_generation_consistency
                where status = 'active'
                  and consistency_status = 'inconsistent'
                """
            )
            workbench_consistency_unavailable_count = _optional_int(
                (consistency_row or {}).get("inconsistent_count")
            ) or 0
        except Exception:
            workbench_consistency_warning = "workbench_generation_consistency_unavailable"
        durations_by_event_type: dict[str, dict[str, Any]] = {}
        for row in duration_rows:
            event_type = str(row.get("event_type") or "")
            if not event_type:
                continue
            window_name = str(row.get("window_name") or "all_time")
            refresh_kind = str(row.get("refresh_kind") or "unknown")
            event_payload = durations_by_event_type.setdefault(event_type, {"windows": {}, "kinds": {}})
            window_payload = event_payload["windows"].setdefault(
                window_name,
                {
                    "sample_count": 0,
                    "last_completed_at": None,
                    "duration_ms": dict(EMPTY_PERCENTILES),
                },
            )
            sample_count = _optional_int(row.get("sample_count")) or 0
            if sample_count > int(window_payload["sample_count"]):
                window_payload["sample_count"] = sample_count
                window_payload["last_completed_at"] = row.get("last_completed_at")
                window_payload["duration_ms"] = {
                    "p50": _optional_float(row.get("p50_ms")),
                    "p95": _optional_float(row.get("p95_ms")),
                    "p99": _optional_float(row.get("p99_ms")),
                }
            event_payload["kinds"].setdefault(refresh_kind, {})[window_name] = {
                "sample_count": sample_count,
                "last_completed_at": row.get("last_completed_at"),
                "duration_ms": {
                    "p50": _optional_float(row.get("p50_ms")),
                    "p95": _optional_float(row.get("p95_ms")),
                    "p99": _optional_float(row.get("p99_ms")),
                },
            }
        dirty_by_scope_type = {str(row.get("scope_type")): row for row in dirty_rows}
        rows: list[dict[str, Any]] = []
        for event_type, (key, scope_type) in READ_MODEL_EVENT_TYPES.items():
            duration = durations_by_event_type.get(event_type, {})
            windows = duration.get("windows") if isinstance(duration.get("windows"), dict) else {}
            recent_15m = windows.get("recent_15m") if isinstance(windows.get("recent_15m"), dict) else {}
            all_time = windows.get("all_time") if isinstance(windows.get("all_time"), dict) else {}
            dirty = dirty_by_scope_type.get(scope_type, {})
            unavailable_count = _optional_int(dirty.get("unavailable_count")) or 0
            warning_code = None
            if key == "workbench":
                unavailable_count += workbench_consistency_unavailable_count
                warning_code = workbench_consistency_warning
            rows.append(
                {
                    "key": key,
                    "refresh_duration_ms": recent_15m.get("duration_ms") or dict(EMPTY_PERCENTILES),
                    "refresh_duration_windows": {
                        "recent_15m": recent_15m
                        or {"sample_count": 0, "last_completed_at": None, "duration_ms": dict(EMPTY_PERCENTILES)},
                        "recent_1h": windows.get("recent_1h")
                        or {"sample_count": 0, "last_completed_at": None, "duration_ms": dict(EMPTY_PERCENTILES)},
                    },
                    "historical_refresh_duration_ms": all_time.get("duration_ms") or dict(EMPTY_PERCENTILES),
                    "refresh_duration_by_kind": duration.get("kinds") if isinstance(duration.get("kinds"), dict) else {},
                    "stale_count": _optional_int(dirty.get("stale_count")) or 0,
                    "unavailable_count": unavailable_count,
                    "status": "available",
                    **({"warning_code": warning_code} if warning_code else {}),
                }
            )
        return rows

    def dashboard_worker_metrics(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select distinct on (worker_kind)
              worker_id,
              worker_kind,
              status,
              extract(epoch from now() - last_seen_at)::float as heartbeat_lag_seconds
            from job.runtime_worker_heartbeats
            where worker_kind <> 'runtime'
            order by worker_kind, last_seen_at desc
            """
        )
        latest_by_kind: dict[str, dict[str, Any]] = {
            str(row.get("worker_kind") or "unknown"): row
            for row in rows
        }
        registrations_by_kind = registration_by_worker_kind()
        worker_rows: list[dict[str, Any]] = []
        emitted: set[str] = set()
        for registration in worker_registrations(required_only=True):
            row = latest_by_kind.get(registration.worker_kind)
            emitted.add(registration.worker_kind)
            if row is None:
                worker_rows.append(
                    {
                        "worker_id": "",
                        "worker_kind": registration.worker_kind,
                        "worker_status": "missing",
                        "heartbeat_lag_seconds": None,
                        "required": True,
                        "expected_event_types": list(registration.event_types),
                        "expected_transport": "rabbitmq_or_postgres" if registration.rabbitmq_eligible else "postgres",
                        "status": "missing",
                        "warning_code": "required_worker_missing",
                    }
                )
                continue
            worker_rows.append(_worker_metric_row(row, registration=registration, required=True))
        for worker_kind, row in latest_by_kind.items():
            if worker_kind in emitted:
                continue
            registration = registrations_by_kind.get(worker_kind)
            worker_rows.append(_worker_metric_row(row, registration=registration, required=False))
        return worker_rows


def _rabbitmq_dispatch_event_types() -> tuple[str, ...]:
    try:
        return RuntimeQueueSettings.from_env().rabbitmq_dispatch_event_types
    except Exception:
        return DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _worker_metric_row(
    row: dict[str, Any],
    *,
    registration: Any | None,
    required: bool,
) -> dict[str, Any]:
    heartbeat_lag_seconds = _optional_float(row.get("heartbeat_lag_seconds"))
    stale_after_seconds = (
        int(registration.heartbeat_stale_after_seconds)
        if registration is not None
        else None
    )
    is_stale = (
        required
        and heartbeat_lag_seconds is not None
        and stale_after_seconds is not None
        and heartbeat_lag_seconds > stale_after_seconds
    )
    payload = {
        "worker_id": str(row.get("worker_id") or ""),
        "worker_kind": str(row.get("worker_kind") or "unknown"),
        "worker_status": str(row.get("status") or ""),
        "heartbeat_lag_seconds": heartbeat_lag_seconds,
        "required": required,
        "expected_event_types": list(registration.event_types) if registration is not None else [],
        "expected_transport": (
            "rabbitmq_or_postgres"
            if registration is not None and registration.rabbitmq_eligible
            else "postgres"
            if registration is not None
            else "unknown"
        ),
        "status": "stale" if is_stale else "available",
    }
    if is_stale:
        payload["warning_code"] = "worker_heartbeat_stale"
    return payload
