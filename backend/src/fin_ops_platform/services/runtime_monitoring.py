from __future__ import annotations

from typing import Any

from fin_ops_platform.services.runtime_worker_registry import registration_by_worker_kind, worker_registrations


def readiness_blockers(
    *,
    storage_backend: str,
    postgres_status: object,
    runtime_release: dict[str, object],
    production_runtime_guard: dict[str, object],
    runtime_infrastructure: dict[str, object],
) -> dict[str, object]:
    """Return bounded infrastructure blockers for the production API runtime."""
    blockers: dict[str, object] = {}
    if not bool(runtime_release.get("consistent")):
        blockers["runtime_release_inconsistent"] = runtime_release.get("problems") or True
    if not bool(production_runtime_guard.get("consistent")):
        blockers["production_runtime_guard_failed"] = production_runtime_guard.get("problems") or True
    if storage_backend != "postgres":
        return blockers
    if str(postgres_status or "").strip().lower() != "ready":
        blockers["postgres_unavailable"] = str(postgres_status or "unknown")
    if not runtime_infrastructure or str(runtime_infrastructure.get("status") or "").strip().lower() == "error":
        blockers["runtime_monitoring_unavailable"] = True
        return blockers
    for field, code in (
        ("missing_required_worker_count", "required_worker_missing"),
        ("stale_required_worker_count", "required_worker_stale"),
        ("mismatched_required_worker_count", "required_worker_mismatch"),
        ("critical_failed_outbox_count", "critical_outbox_failed"),
    ):
        count = int(runtime_infrastructure.get(field) or 0)
        if count > 0:
            blockers[code] = count
    return blockers


class RuntimeMonitoringRepository:
    """Monitoring for the durable PostgreSQL queue and registered workers."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def app_status_runtime_snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            return {
                "outbox_statuses": self._app_status_outbox_statuses(),
                "worker_statuses": self._app_status_worker_statuses(),
            }
        except Exception as exc:
            payload = {"status": "unavailable", "last_error": str(exc) or exc.__class__.__name__}
            return {
                "outbox_statuses": {"__runtime__": dict(payload)},
                "worker_statuses": {"__runtime__": dict(payload)},
            }

    def _app_status_outbox_statuses(self) -> dict[str, dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select
              event_type,
              coalesce(scope_type, raw_payload->>'scope_type', aggregate_type, '') as scope_type,
              coalesce(scope_key, raw_payload->>'scope_key', aggregate_id, '') as scope_key,
              case
                when status in ('failed', 'dead_lettered') then status
                else status
              end as status,
              count(*)::bigint as count,
              max(last_error) as last_error,
              max(updated_at)::text as updated_at
            from job.outbox_events
            where status in ('pending', 'processing', 'failed', 'dead_lettered')
              and not (
                event_type = 'oa.sync'
                and coalesce(payload->>'operation', '') = 'refresh_attachments'
              )
            group by event_type, 2, 3, 4
            """
        )
        grouped: dict[str, dict[str, Any]] = {}
        scopes_by_event: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            event_type = str(row.get("event_type") or "").strip()
            if not event_type:
                continue
            row_status = str(row.get("status") or "ready").strip().lower()
            current = grouped.setdefault(event_type, {"status": "ready", "count": 0})
            current["count"] = int(current.get("count") or 0) + int(row.get("count") or 0)
            current["status"] = _max_app_outbox_status(str(current.get("status") or "ready"), row_status)
            if row.get("last_error"):
                current["last_error"] = str(row.get("last_error") or "")
            if row.get("updated_at"):
                current["updated_at"] = str(row.get("updated_at") or "")
            scope_type = str(row.get("scope_type") or "")
            scope_key = str(row.get("scope_key") or "")
            if scope_type or scope_key:
                scopes_by_event.setdefault(event_type, []).append(
                    {
                        "event_type": event_type,
                        "scope_type": scope_type,
                        "scope_key": scope_key,
                        "status": row_status,
                        "count": int(row.get("count") or 0),
                        "last_error": str(row.get("last_error") or ""),
                        "updated_at": str(row.get("updated_at") or ""),
                    }
                )
        for event_type, scopes in scopes_by_event.items():
            grouped[event_type]["scopes"] = scopes
        return grouped

    def _app_status_worker_statuses(self) -> dict[str, dict[str, Any]]:
        statuses: dict[str, dict[str, Any]] = {}
        registered_instances = {registration.instance_name for registration in worker_registrations(required_only=True)}
        for row in self.dashboard_worker_metrics():
            instance = str(row.get("worker_instance") or "").strip()
            if not instance or instance not in registered_instances:
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
        return self.ready_health_summary(stale_after_seconds=stale_after_seconds)

    def ready_health_summary(
        self,
        *,
        stale_after_seconds: int = 300,
        required_worker_instances: set[str] | None = None,
    ) -> dict[str, Any]:
        del stale_after_seconds
        outbox_summary = self._ready_outbox_summary()
        worker_lag_row = self._connection.fetch_one(
            """
            with latest_worker_kind_heartbeats as (
              select distinct on (worker_kind) worker_kind, last_seen_at
              from job.runtime_worker_heartbeats
              order by worker_kind, last_seen_at desc
            )
            select extract(epoch from max(now() - last_seen_at))::float
                     as max_worker_heartbeat_lag_seconds
            from latest_worker_kind_heartbeats
            where worker_kind <> 'runtime'
            """
        )
        worker_metrics = self.dashboard_worker_metrics(worker_instances=required_worker_instances)
        missing_count = sum(1 for row in worker_metrics if row.get("warning_code") == "required_worker_missing")
        stale_count = sum(1 for row in worker_metrics if row.get("warning_code") == "worker_heartbeat_stale")
        mismatched_count = sum(
            1
            for row in worker_metrics
            if row.get("required") and row.get("warning_code") in {"worker_kind_mismatch", "worker_event_type_mismatch"}
        )
        queue_backlog = outbox_summary["queue_backlog"]
        return {
            "queue_backlog": queue_backlog,
            "failed_jobs": int(queue_backlog.get("failed", 0)) + int(queue_backlog.get("dead_lettered", 0)),
            "max_pending_age_seconds": outbox_summary["max_pending_age_seconds"],
            "oldest_pending_event_age_seconds": outbox_summary["max_pending_age_seconds"],
            "worker_heartbeat_lag_seconds": (worker_lag_row or {}).get("max_worker_heartbeat_lag_seconds"),
            "worker_metrics": worker_metrics,
            "missing_required_worker_count": missing_count,
            "stale_required_worker_count": stale_count,
            "mismatched_required_worker_count": mismatched_count,
            "critical_failed_outbox_count": outbox_summary["critical_failed_outbox_count"],
            "pending_outbox_events_by_scope": outbox_summary["pending_outbox_events_by_scope"],
        }

    def _ready_outbox_summary(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            /* ready_outbox_snapshot */
            with current_events as materialized (
              select event_type, status,
                     coalesce(scope_type, raw_payload->>'scope_type', aggregate_type, '') as scope_type,
                     coalesce(scope_key, raw_payload->>'scope_key', aggregate_id, '') as scope_key,
                     created_at, attempts, last_error
              from job.outbox_events
              where status <> 'done'
                and not (
                  event_type = 'oa.sync'
                  and coalesce(payload->>'operation', '') = 'refresh_attachments'
                )
            ),
            queue_counts as (
              select status, count(*)::bigint as count
              from current_events where status <> 'done' group by status
            ),
            scope_rows as (
              select event_type, status, scope_type, scope_key, count(*)::bigint as count,
                     extract(epoch from max(now() - created_at))::float as oldest_age_seconds,
                     max(attempts)::integer as attempts, max(coalesce(last_error, '')) as last_error
              from current_events
              where status in ('pending', 'processing', 'failed', 'dead_lettered')
              group by event_type, status, scope_type, scope_key
              order by oldest_age_seconds desc nulls last
              limit 30
            )
            select
              coalesce((select jsonb_object_agg(status, count) from queue_counts), '{}'::jsonb) as queue_backlog,
              (select extract(epoch from max(now() - created_at))::float from current_events where status = 'pending')
                as max_pending_age_seconds,
              coalesce((select jsonb_agg(to_jsonb(scope_rows)) from scope_rows), '[]'::jsonb)
                as pending_outbox_events_by_scope,
              (select count(*)::bigint from current_events where status in ('failed', 'dead_lettered'))
                as critical_failed_outbox_count
            """,
        )
        payload = row if isinstance(row, dict) else {}
        queue_payload = payload.get("queue_backlog") if isinstance(payload.get("queue_backlog"), dict) else {}
        scope_rows = payload.get("pending_outbox_events_by_scope") if isinstance(payload.get("pending_outbox_events_by_scope"), list) else []
        return {
            "queue_backlog": {str(key): int(value or 0) for key, value in queue_payload.items()},
            "max_pending_age_seconds": payload.get("max_pending_age_seconds"),
            "critical_failed_outbox_count": int(payload.get("critical_failed_outbox_count") or 0),
            "pending_outbox_events_by_scope": [
                {
                    "event_type": str(scope.get("event_type") or ""),
                    "status": str(scope.get("status") or ""),
                    "scope_type": str(scope.get("scope_type") or ""),
                    "scope_key": str(scope.get("scope_key") or ""),
                    "count": int(scope.get("count") or 0),
                    "oldest_age_seconds": scope.get("oldest_age_seconds"),
                    "attempts": int(scope.get("attempts") or 0),
                    "last_error": str(scope.get("last_error") or ""),
                }
                for scope in scope_rows
                if isinstance(scope, dict)
            ],
        }

    def dashboard_outbox_metric(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select
              count(*) filter (where status = 'pending')::bigint as pending_count,
              count(*) filter (where status = 'processing')::bigint as processing_count,
              count(*) filter (where status in ('failed', 'dead_lettered'))::bigint as failed_count,
              extract(epoch from max(now() - created_at) filter (where status = 'pending'))::float
                as oldest_pending_age_seconds
            from job.outbox_events
            where status in ('pending', 'processing', 'failed', 'dead_lettered')
            """
        ) or {}
        return {
            "pending_count": _optional_int(row.get("pending_count")),
            "processing_count": _optional_int(row.get("processing_count")),
            "failed_count": _optional_int(row.get("failed_count")),
            "oldest_pending_age_seconds": _optional_float(row.get("oldest_pending_age_seconds")),
            "status": "available",
        }

    def dashboard_queue_metrics(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select event_type,
                   count(*) filter (where status = 'pending')::bigint as pending_count,
                   count(*) filter (where status = 'processing')::bigint as processing_count,
                   count(*) filter (where status in ('failed', 'dead_lettered'))::bigint as failed_count
            from job.outbox_events
            where status in ('pending', 'processing', 'failed', 'dead_lettered')
            group by event_type
            order by event_type
            """
        )
        return [
            {
                "event_type": str(row.get("event_type") or ""),
                "queue": "job.outbox_events",
                "pending_count": _optional_int(row.get("pending_count")),
                "processing_count": _optional_int(row.get("processing_count")),
                "failed_count": _optional_int(row.get("failed_count")),
                "status": "available",
            }
            for row in rows
        ]

    def dashboard_worker_metrics(self, *, worker_instances: set[str] | None = None) -> list[dict[str, Any]]:
        normalized_instances = {str(instance).strip() for instance in set(worker_instances or set()) if str(instance).strip()}
        registrations = worker_registrations(required_only=True)
        if worker_instances is not None:
            registrations = [registration for registration in registrations if registration.instance_name in normalized_instances]
        worker_kinds = sorted({registration.worker_kind for registration in registrations})
        worker_filter_sql = ""
        worker_filter_params: tuple[object, ...] = ()
        if worker_instances is not None:
            worker_filter_sql = """
              and (
                coalesce(payload->>'worker_instance', worker_kind) = any(%s::text[])
                or worker_kind = any(%s::text[])
              )
            """
            worker_filter_params = (sorted(normalized_instances), worker_kinds)
        rows = self._connection.fetch_all(
            f"""
            select distinct on (coalesce(payload->>'worker_instance', worker_kind))
              worker_id, coalesce(payload->>'worker_instance', worker_kind) as worker_instance,
              worker_kind, status,
              extract(epoch from now() - last_seen_at)::float as heartbeat_lag_seconds,
              payload
            from job.runtime_worker_heartbeats
            where worker_kind <> 'runtime' {worker_filter_sql}
            order by coalesce(payload->>'worker_instance', worker_kind), last_seen_at desc
            """,
            worker_filter_params,
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
        for registration in registrations:
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
                        "expected_transport": "postgres",
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
            if worker_instances is not None and worker_instance not in normalized_instances:
                continue
            if worker_instance in emitted_instances:
                continue
            worker_id = str(row.get("worker_id") or "").strip()
            if worker_id and worker_id in emitted_worker_ids:
                continue
            registration = registrations_by_kind.get(str(row.get("worker_kind") or "unknown"))
            worker_rows.append(_worker_metric_row(row, registration=registration, required=False))
        return worker_rows


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


def _max_app_outbox_status(left: str, right: str) -> str:
    normalized = "failed" if right in {"failed", "dead_lettered"} else right
    rank = {"ready": 0, "pending": 1, "processing": 2, "failed": 3}
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


def _worker_metric_row(row: dict[str, Any], *, registration: Any | None, required: bool) -> dict[str, Any]:
    heartbeat_lag_seconds = _optional_float(row.get("heartbeat_lag_seconds"))
    worker_instance = str(row.get("worker_instance") or "")
    worker_kind = str(row.get("worker_kind") or "unknown")
    heartbeat_payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    configured_event_types = _string_list(heartbeat_payload.get("configured_event_types"))
    expected_event_types = list(registration.event_types) if registration is not None else []
    stale_after_seconds = int(registration.heartbeat_stale_after_seconds) if registration is not None else None
    is_stale = (
        required
        and heartbeat_lag_seconds is not None
        and stale_after_seconds is not None
        and heartbeat_lag_seconds > stale_after_seconds
    )
    warning_code = None
    if registration is not None and worker_kind != registration.worker_kind:
        warning_code = "worker_kind_mismatch"
    elif registration is not None and configured_event_types and tuple(configured_event_types) not in {
        tuple(registration.event_types),
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
        "current_effective": required or registration is not None,
        "required": required,
        "expected_event_types": expected_event_types,
        "configured_event_types": configured_event_types,
        "expected_transport": "postgres" if registration is not None else "unknown",
        "status": "stale" if is_stale else "mismatch" if warning_code else "available",
    }
    if warning_code:
        payload["warning_code"] = warning_code
    return payload


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]
