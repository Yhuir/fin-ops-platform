from __future__ import annotations

from typing import Any

from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueSettings


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
            select extract(epoch from max(now() - last_seen_at))::float as max_worker_heartbeat_lag_seconds
            from job.runtime_worker_heartbeats
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


def _rabbitmq_dispatch_event_types() -> tuple[str, ...]:
    try:
        return RuntimeQueueSettings.from_env().rabbitmq_dispatch_event_types
    except Exception:
        return DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES
