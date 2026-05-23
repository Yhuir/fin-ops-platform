from __future__ import annotations

from typing import Any

from fin_ops_platform.services.rabbitmq_runtime import rabbitmq_event_routes
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueSettings


READ_MODEL_EVENT_TYPES: dict[str, tuple[str, str]] = {
    "workbench.read_model.refresh": ("workbench", "workbench"),
    "search.read_model.refresh": ("search", "search"),
    "pending_invoice.read_model.refresh": ("pending_invoice", "pending_invoice"),
    "cost_statistics.read_model.refresh": ("cost_statistics", "cost_statistics"),
    "tax_offset.read_model.refresh": ("tax_offset", "tax_offset"),
}

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
        return {
            "queue_backlog": queue_backlog,
            "dirty_scopes": dirty_scopes,
            "failed_jobs": int(queue_backlog.get("failed", 0)) + int(queue_backlog.get("dead_lettered", 0)),
            "max_pending_age_seconds": max_pending_age_seconds,
            "oldest_pending_event_age_seconds": max_pending_age_seconds,
            "worker_heartbeat_lag_seconds": (worker_lag_row or {}).get("max_worker_heartbeat_lag_seconds"),
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
            select
              event_type,
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
            where event_type = any(%s)
              and status = 'done'
              and raw_payload->'runtime_result' ? 'duration_ms'
            group by event_type
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
        duration_by_event_type = {str(row.get("event_type")): row for row in duration_rows}
        dirty_by_scope_type = {str(row.get("scope_type")): row for row in dirty_rows}
        rows: list[dict[str, Any]] = []
        for event_type, (key, scope_type) in READ_MODEL_EVENT_TYPES.items():
            duration = duration_by_event_type.get(event_type, {})
            dirty = dirty_by_scope_type.get(scope_type, {})
            rows.append(
                {
                    "key": key,
                    "refresh_duration_ms": {
                        "p50": _optional_float(duration.get("p50_ms")),
                        "p95": _optional_float(duration.get("p95_ms")),
                        "p99": _optional_float(duration.get("p99_ms")),
                    },
                    "stale_count": _optional_int(dirty.get("stale_count")) or 0,
                    "unavailable_count": _optional_int(dirty.get("unavailable_count")) or 0,
                    "status": "available",
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
        return [
            {
                "worker_id": str(row.get("worker_id") or ""),
                "worker_kind": str(row.get("worker_kind") or "unknown"),
                "worker_status": str(row.get("status") or ""),
                "heartbeat_lag_seconds": _optional_float(row.get("heartbeat_lag_seconds")),
                "status": "available",
            }
            for row in rows
        ]


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
