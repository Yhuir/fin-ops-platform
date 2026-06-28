from __future__ import annotations

from typing import Any

from fin_ops_platform.services.rabbitmq_runtime import rabbitmq_event_routes
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueSettings
from fin_ops_platform.services.runtime_worker_registry import (
    registration_by_worker_kind,
    worker_registrations,
)


RABBITMQ_PUBLISH_CONFIRM_METRIC_SAMPLE_LIMIT = 512

def _current_effective_outbox_attention_predicate_sql(alias: str) -> str:
    prefix = f"{alias}."
    scope_type_expr = (
        f"coalesce({prefix}scope_type, {prefix}raw_payload->>'scope_type', "
        f"{prefix}payload->>'scope_type', {prefix}aggregate_type, '')"
    )
    scope_key_expr = (
        f"coalesce({prefix}scope_key, {prefix}raw_payload->>'scope_key', "
        f"{prefix}payload->>'scope_key', {prefix}aggregate_id, '')"
    )
    return f"""
not (
  exists (
    select 1
    from job.outbox_events newer
    where newer.tenant_id = {prefix}tenant_id
      and newer.event_type = {prefix}event_type
      and coalesce(newer.scope_type, newer.raw_payload->>'scope_type', newer.payload->>'scope_type', newer.aggregate_type, '') =
          {scope_type_expr}
      and coalesce(newer.scope_key, newer.raw_payload->>'scope_key', newer.payload->>'scope_key', newer.aggregate_id, '') =
          {scope_key_expr}
      and newer.status in ('pending', 'processing', 'done')
      and newer.id <> {prefix}id
      and (
        newer.created_at > {prefix}created_at
        or (newer.created_at = {prefix}created_at and newer.id > {prefix}id)
      )
  )
  or
  exists (
    select 1
    from job.outbox_events done
    where done.tenant_id = {prefix}tenant_id
      and done.event_type = {prefix}event_type
      and coalesce(done.scope_type, done.raw_payload->>'scope_type', done.payload->>'scope_type', done.aggregate_type, '') =
          {scope_type_expr}
      and coalesce(done.scope_key, done.raw_payload->>'scope_key', done.payload->>'scope_key', done.aggregate_id, '') =
          {scope_key_expr}
      and done.status = 'done'
      and done.updated_at > {prefix}updated_at
  )
)
"""


class RuntimeMonitoringRepository:
    def __init__(self, connection: Any, rabbitmq_metrics_provider: Any | None = None) -> None:
        self._connection = connection
        self._rabbitmq_metrics_provider = rabbitmq_metrics_provider

    def app_status_runtime_snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            return {
                "outbox_statuses": self._app_status_outbox_statuses(),
                "worker_statuses": self._app_status_worker_statuses(),
            }
        except Exception as exc:
            payload = {
                "status": "unavailable",
                "last_error": str(exc) or exc.__class__.__name__,
            }
            return {
                "outbox_statuses": {"__runtime__": dict(payload)},
                "worker_statuses": {"__runtime__": dict(payload)},
            }

    def _app_status_outbox_statuses(self) -> dict[str, dict[str, Any]]:
        rows = self._connection.fetch_all(
            f"""
            select
                e.event_type,
                coalesce(e.scope_type, e.raw_payload->>'scope_type', e.payload->>'scope_type', e.aggregate_type, '') as scope_type,
                coalesce(e.scope_key, e.raw_payload->>'scope_key', e.payload->>'scope_key', e.aggregate_id, '') as scope_key,
                case
                  when e.status in ('failed', 'dead_lettered') then e.status
                  when e.publish_status = 'failed' then 'publish_failed'
                  when e.publish_status = 'publishing' then 'publishing'
                  else e.status
                end as status,
                count(*)::bigint as count,
                max(e.last_error) as last_error,
                max(e.updated_at)::text as updated_at,
                bool_or(
                    exists (
                        select 1
                        from job.outbox_events newer
                        where newer.tenant_id = e.tenant_id
                          and newer.event_type = e.event_type
                          and coalesce(newer.scope_type, newer.raw_payload->>'scope_type', newer.payload->>'scope_type', newer.aggregate_type, '') =
                              coalesce(e.scope_type, e.raw_payload->>'scope_type', e.payload->>'scope_type', e.aggregate_type, '')
                          and coalesce(newer.scope_key, newer.raw_payload->>'scope_key', newer.payload->>'scope_key', newer.aggregate_id, '') =
                              coalesce(e.scope_key, e.raw_payload->>'scope_key', e.payload->>'scope_key', e.aggregate_id, '')
                          and newer.status in ('pending', 'processing', 'done')
                          and newer.id <> e.id
                          and (
                            newer.created_at > e.created_at
                            or (newer.created_at = e.created_at and newer.id > e.id)
                          )
                    )
                ) as covered_by_later_event,
                bool_or(
                    exists (
                        select 1
                        from job.outbox_events done
                        where done.tenant_id = e.tenant_id
                          and done.event_type = e.event_type
                          and coalesce(done.scope_type, done.raw_payload->>'scope_type', done.payload->>'scope_type', done.aggregate_type, '') =
                              coalesce(e.scope_type, e.raw_payload->>'scope_type', e.payload->>'scope_type', e.aggregate_type, '')
                          and coalesce(done.scope_key, done.raw_payload->>'scope_key', done.payload->>'scope_key', done.aggregate_id, '') =
                              coalesce(e.scope_key, e.raw_payload->>'scope_key', e.payload->>'scope_key', e.aggregate_id, '')
                          and done.status = 'done'
                          and done.updated_at > e.updated_at
                    )
                ) as covered_by_later_done
            from job.outbox_events e
            where (
                e.status in ('pending', 'processing', 'publishing', 'publish_failed', 'failed', 'dead_lettered')
                or (
                    e.status <> 'done'
                    and e.publish_status in ('publishing', 'failed')
                )
            )
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.event_type, 2, 3, 4
            """
        )
        grouped: dict[str, dict[str, Any]] = {}
        scope_indexes: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
        for row in rows:
            event_type = str(row.get("event_type") or "").strip()
            if not event_type:
                continue
            if _is_historical_outbox_status(row):
                continue
            row_count = _optional_int(row.get("count")) or 0
            row_status = str(row.get("status") or "")
            updated_at = str(row.get("updated_at") or "").strip()
            last_error = str(row.get("last_error") or "").strip()
            current = grouped.setdefault(event_type, {"status": "ready", "count": 0})
            current["count"] = int(current.get("count") or 0) + row_count
            current["status"] = _max_app_outbox_status(
                str(current.get("status") or "ready"),
                row_status,
            )
            if last_error:
                current["last_error"] = last_error
            if updated_at:
                current["updated_at"] = updated_at
            scope_type = str(row.get("scope_type") or "").strip()
            scope_key = str(row.get("scope_key") or "").strip()
            if scope_type or scope_key:
                scope_index = scope_indexes.setdefault(event_type, {})
                scope_payload = scope_index.setdefault(
                    (scope_type, scope_key),
                    {
                        "event_type": event_type,
                        "scope_type": scope_type,
                        "scope_key": scope_key,
                        "status": "ready",
                        "count": 0,
                    },
                )
                scope_payload["count"] = int(scope_payload.get("count") or 0) + row_count
                scope_payload["status"] = _max_app_outbox_status(
                    str(scope_payload.get("status") or "ready"),
                    row_status,
                )
                if last_error:
                    scope_payload["last_error"] = last_error
                if updated_at:
                    scope_payload["updated_at"] = updated_at
        for event_type, scope_index in scope_indexes.items():
            if event_type in grouped:
                grouped[event_type]["scopes"] = list(scope_index.values())
        return grouped

    def _app_status_worker_statuses(self) -> dict[str, dict[str, Any]]:
        statuses: dict[str, dict[str, Any]] = {}
        for row in self.dashboard_worker_metrics():
            if row.get("required") is False and row.get("current_effective") is False:
                continue
            instance = str(row.get("worker_instance") or "").strip()
            if not instance:
                continue
            statuses[instance] = {
                "status": _app_status_worker_status(row.get("status")),
                "worker_id": row.get("worker_id"),
                "worker_kind": row.get("worker_kind"),
                "heartbeat_lag_seconds": row.get("heartbeat_lag_seconds"),
                "warning_code": row.get("warning_code"),
                "required": row.get("required"),
            }
        return statuses

    def health_summary(self, *, stale_after_seconds: int = 300) -> dict[str, Any]:
        queue_rows = self._connection.fetch_all(
            f"""
            select e.status, count(*)::bigint as count
            from job.outbox_events e
            where e.status <> 'done'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.status
            order by e.status
            """
        )
        age_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_pending_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """
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
        publish_rows = self._connection.fetch_all(
            f"""
            select e.publish_status, count(*)::bigint as count
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.publish_status
            order by e.publish_status
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_lag_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_unpublished_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and e.publish_status in ('unpublished', 'failed')
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_confirm_latency_row = self._connection.fetch_one(
            """
            with event_type_filter(event_type) as (
              select unnest(%s::text[])
            ),
            recent_publish_confirms as (
              select
                ((published_event.raw_payload->'rabbitmq_publish'->>'confirm_latency_ms')::numeric) as confirm_latency_ms
              from event_type_filter
              cross join lateral (
                select raw_payload, updated_at
                from job.outbox_events
                where event_type = event_type_filter.event_type
                  and publish_status = 'published'
                  and raw_payload->'rabbitmq_publish' ? 'confirm_latency_ms'
                order by updated_at desc
                limit %s
              ) published_event
            )
            select
              percentile_cont(0.5) within group (
                order by confirm_latency_ms
              )::float as p50_ms,
              percentile_cont(0.95) within group (
                order by confirm_latency_ms
              )::float as p95_ms,
              percentile_cont(0.99) within group (
                order by confirm_latency_ms
              )::float as p99_ms
            from recent_publish_confirms
            """,
            (list(_rabbitmq_dispatch_event_types()), RABBITMQ_PUBLISH_CONFIRM_METRIC_SAMPLE_LIMIT),
        )
        pending_outbox_by_scope = self._pending_outbox_events_by_scope()
        queue_backlog = {str(row["status"]): int(row["count"]) for row in queue_rows}
        publish_status = {str(row["publish_status"]): int(row["count"]) for row in publish_rows}
        max_pending_age_seconds = (age_row or {}).get("max_pending_age_seconds")
        rabbitmq_metrics = self._rabbitmq_metrics()
        worker_metrics = self.dashboard_worker_metrics()
        missing_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "required_worker_missing")
        stale_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "worker_heartbeat_stale")
        mismatched_required_worker_count = sum(
            1
            for row in worker_metrics
            if row.get("required") and row.get("warning_code") in {"worker_kind_mismatch", "worker_event_type_mismatch"}
        )
        return {
            "queue_backlog": queue_backlog,
            "failed_jobs": int(queue_backlog.get("failed", 0)) + int(queue_backlog.get("dead_lettered", 0)),
            "max_pending_age_seconds": max_pending_age_seconds,
            "oldest_pending_event_age_seconds": max_pending_age_seconds,
            "worker_heartbeat_lag_seconds": (worker_lag_row or {}).get("max_worker_heartbeat_lag_seconds"),
            "worker_metrics": worker_metrics,
            "missing_required_worker_count": missing_required_worker_count,
            "stale_required_worker_count": stale_required_worker_count,
            "mismatched_required_worker_count": mismatched_required_worker_count,
            "rabbitmq_publish_status": publish_status,
            "rabbitmq_unpublished_backlog": int(publish_status.get("unpublished", 0)),
            "rabbitmq_publish_failed_backlog": int(publish_status.get("failed", 0)),
            "rabbitmq_dispatcher_lag_seconds": (publish_lag_row or {}).get("max_unpublished_age_seconds"),
            "rabbitmq_publish_confirm_latency_ms": {
                "p50": (publish_confirm_latency_row or {}).get("p50_ms"),
                "p95": (publish_confirm_latency_row or {}).get("p95_ms"),
                "p99": (publish_confirm_latency_row or {}).get("p99_ms"),
            },
            "rabbitmq_publish_confirm_sample_limit": RABBITMQ_PUBLISH_CONFIRM_METRIC_SAMPLE_LIMIT,
            "rabbitmq_dispatch_event_types": list(_rabbitmq_dispatch_event_types()),
            **rabbitmq_metrics,
            "pending_outbox_events_by_scope": pending_outbox_by_scope,
        }

    def ready_health_summary(self, *, stale_after_seconds: int = 300) -> dict[str, Any]:
        queue_rows = self._connection.fetch_all(
            f"""
            select e.status, count(*)::bigint as count
            from job.outbox_events e
            where e.status <> 'done'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.status
            order by e.status
            """
        )
        age_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_pending_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """
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
        publish_rows = self._connection.fetch_all(
            f"""
            select e.publish_status, count(*)::bigint as count
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.publish_status
            order by e.publish_status
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_lag_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_unpublished_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and e.publish_status in ('unpublished', 'failed')
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        pending_outbox_by_scope = self._pending_outbox_events_by_scope()
        queue_backlog = {str(row["status"]): int(row["count"]) for row in queue_rows}
        publish_status = {str(row["publish_status"]): int(row["count"]) for row in publish_rows}
        worker_metrics = self.dashboard_worker_metrics()
        missing_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "required_worker_missing")
        stale_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "worker_heartbeat_stale")
        mismatched_required_worker_count = sum(
            1
            for row in worker_metrics
            if row.get("required") and row.get("warning_code") in {"worker_kind_mismatch", "worker_event_type_mismatch"}
        )
        rabbitmq_metrics = self._rabbitmq_metrics()
        max_pending_age_seconds = (age_row or {}).get("max_pending_age_seconds")
        return {
            "queue_backlog": queue_backlog,
            "failed_jobs": int(queue_backlog.get("failed", 0)) + int(queue_backlog.get("dead_lettered", 0)),
            "max_pending_age_seconds": max_pending_age_seconds,
            "oldest_pending_event_age_seconds": max_pending_age_seconds,
            "worker_heartbeat_lag_seconds": (worker_lag_row or {}).get("max_worker_heartbeat_lag_seconds"),
            "worker_metrics": worker_metrics,
            "missing_required_worker_count": missing_required_worker_count,
            "stale_required_worker_count": stale_required_worker_count,
            "mismatched_required_worker_count": mismatched_required_worker_count,
            "rabbitmq_publish_status": publish_status,
            "rabbitmq_unpublished_backlog": int(publish_status.get("unpublished", 0)),
            "rabbitmq_publish_failed_backlog": int(publish_status.get("failed", 0)),
            "rabbitmq_dispatcher_lag_seconds": (publish_lag_row or {}).get("max_unpublished_age_seconds"),
            **rabbitmq_metrics,
            "pending_outbox_events_by_scope": pending_outbox_by_scope,
        }

    def _pending_outbox_events_by_scope(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            f"""
            with pending_outbox_by_scope as (
              select
                e.event_type,
                e.status,
                coalesce(e.scope_type, e.raw_payload->>'scope_type', e.aggregate_type, '') as scope_type,
                coalesce(e.scope_key, e.raw_payload->>'scope_key', e.aggregate_id, '') as scope_key,
                count(*)::bigint as count,
                extract(epoch from max(now() - e.created_at))::float as oldest_age_seconds,
                max(e.attempts)::integer as attempts,
                max(coalesce(e.last_error, '')) as last_error
              from job.outbox_events e
              where e.status in ('pending', 'processing', 'failed', 'dead_lettered')
                and {_current_effective_outbox_attention_predicate_sql("e")}
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
            f"""
            select
              count(*) filter (where e.status = 'pending')::bigint as pending_count,
              count(*) filter (where e.publish_status = 'publishing')::bigint as publishing_count,
              count(*) filter (where e.status in ('failed', 'dead_lettered'))::bigint as failed_count,
              count(*) filter (where e.publish_status = 'failed')::bigint as publish_failed_count,
              extract(epoch from max(now() - e.created_at) filter (where e.status = 'pending'))::float
                as oldest_pending_age_seconds
            from job.outbox_events e
            where (
                e.status in ('pending', 'failed', 'dead_lettered')
                or e.publish_status in ('publishing', 'failed')
              )
              and {_current_effective_outbox_attention_predicate_sql("e")}
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

    def dashboard_worker_metrics(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select distinct on (coalesce(payload->>'worker_instance', worker_kind))
              worker_id,
              coalesce(payload->>'worker_instance', worker_kind) as worker_instance,
              worker_kind,
              status,
              extract(epoch from now() - last_seen_at)::float as heartbeat_lag_seconds,
              payload
            from job.runtime_worker_heartbeats
            where worker_kind <> 'runtime'
            order by coalesce(payload->>'worker_instance', worker_kind), last_seen_at desc
            """
        )
        latest_by_instance: dict[str, dict[str, Any]] = {}
        latest_by_kind: dict[str, dict[str, Any]] = {}
        for row in rows:
            worker_instance = str(row.get("worker_instance") or "").strip()
            worker_kind = str(row.get("worker_kind") or "").strip()
            if worker_instance:
                latest_by_instance[worker_instance] = row
            if worker_kind and worker_kind not in latest_by_kind:
                latest_by_kind[worker_kind] = row
        registrations_by_kind = registration_by_worker_kind()
        worker_rows: list[dict[str, Any]] = []
        emitted_instances: set[str] = set()
        emitted_worker_ids: set[str] = set()
        for registration in worker_registrations(required_only=True):
            row = latest_by_instance.get(registration.instance_name) or latest_by_kind.get(registration.worker_kind)
            emitted_instances.add(registration.instance_name)
            if row is None:
                worker_rows.append(
                    {
                        "worker_id": "",
                        "worker_instance": registration.instance_name,
                        "worker_kind": registration.worker_kind,
                        "expected_worker_kind": registration.worker_kind,
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
            worker_id = str(row.get("worker_id") or "").strip()
            if worker_id:
                emitted_worker_ids.add(worker_id)
            worker_rows.append(_worker_metric_row(row, registration=registration, required=True))
        for row in rows:
            worker_instance = str(row.get("worker_instance") or "").strip()
            if worker_instance in emitted_instances:
                continue
            worker_id = str(row.get("worker_id") or "").strip()
            if worker_id and worker_id in emitted_worker_ids:
                continue
            worker_kind = str(row.get("worker_kind") or "unknown")
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


def _is_legacy_cost_statistics_scope(scope_type: object, scope_key: object) -> bool:
    if str(scope_type or "").strip() != "cost_statistics":
        return False
    key = str(scope_key or "").strip()
    if key == "all":
        return True
    parts = key.split("-")
    return len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 2 and all(part.isdigit() for part in parts)


def _is_historical_outbox_status(row: dict[str, Any]) -> bool:
    if _is_legacy_cost_statistics_scope(row.get("scope_type"), row.get("scope_key")):
        return True
    return (
        _truthy(row.get("covered_by_later_event"))
        or _truthy(row.get("covered_by_later_done"))
    )


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "t", "true", "yes", "y"}


def _max_app_outbox_status(left: str, right: str) -> str:
    normalized = "failed" if right in {"publish_failed", "failed", "dead_lettered"} else right
    normalized = "publishing" if normalized == "processing" else normalized
    rank = {"ready": 0, "pending": 1, "publishing": 2, "failed": 3}
    return normalized if rank.get(normalized, 0) > rank.get(left, 0) else left


def _app_status_worker_status(value: object) -> str:
    status = str(value or "").strip()
    if status == "available":
        return "ready"
    if status in {"missing", "mismatch"}:
        return "unavailable"
    if status == "stale":
        return "stale"
    return status or "ready"


def _worker_metric_row(
    row: dict[str, Any],
    *,
    registration: Any | None,
    required: bool,
) -> dict[str, Any]:
    heartbeat_lag_seconds = _optional_float(row.get("heartbeat_lag_seconds"))
    worker_instance = str(row.get("worker_instance") or "")
    worker_kind = str(row.get("worker_kind") or "unknown")
    payload_value = row.get("payload")
    heartbeat_payload = payload_value if isinstance(payload_value, dict) else {}
    configured_event_types = _string_list(heartbeat_payload.get("configured_event_types"))
    expected_event_types = list(registration.event_types) if registration is not None else []
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
    current_effective = required or not (
        heartbeat_lag_seconds is not None
        and stale_after_seconds is not None
        and heartbeat_lag_seconds > stale_after_seconds
    )
    warning_code = None
    if registration is not None and worker_kind != registration.worker_kind:
        warning_code = "worker_kind_mismatch"
    elif registration is not None and configured_event_types and tuple(configured_event_types) not in {
        tuple(registration.event_types),
        registration.claim_event_types(transport="postgres"),
        registration.claim_event_types(transport="rabbitmq"),
    }:
        warning_code = "worker_event_type_mismatch"
    elif is_stale:
        warning_code = "worker_heartbeat_stale"
    payload = {
        "worker_id": str(row.get("worker_id") or ""),
        "worker_instance": worker_instance,
        "worker_kind": worker_kind,
        "expected_worker_kind": registration.worker_kind if registration is not None else worker_kind,
        "worker_status": str(row.get("status") or ""),
        "heartbeat_lag_seconds": heartbeat_lag_seconds,
        "heartbeat_stale_after_seconds": stale_after_seconds,
        "current_effective": current_effective,
        "required": required,
        "expected_event_types": expected_event_types,
        "configured_event_types": configured_event_types,
        "expected_transport": (
            "rabbitmq_or_postgres"
            if registration is not None and registration.rabbitmq_eligible
            else "postgres"
            if registration is not None
            else "unknown"
        ),
        "status": "stale" if is_stale else "mismatch" if warning_code else "available",
    }
    if warning_code:
        payload["warning_code"] = warning_code
    return payload


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]
