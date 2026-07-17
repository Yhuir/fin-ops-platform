from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresTransaction
from fin_ops_platform.services.runtime_worker_registry import rabbitmq_dispatch_event_types


PRIORITY_VALUES = {"low", "normal", "high", "urgent"}
PUBLISH_STATUS_VALUES = {"unpublished", "publishing", "published", "failed"}
DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES = rabbitmq_dispatch_event_types()


@dataclass(frozen=True)
class RuntimeQueueEvent:
    event_id: str
    tenant_id: str
    event_type: str
    aggregate_type: str | None
    aggregate_id: str | None
    scope_type: str | None
    scope_key: str | None
    dedupe_key: str | None
    payload: dict[str, Any]
    attempts: int
    status: str
    schema_version: int = 1
    source_version: int | None = None
    priority: str = "normal"
    trace_id: str | None = None
    publish_status: str = "unpublished"
    publish_attempt_count: int = 0
    rabbitmq_exchange: str | None = None
    rabbitmq_routing_key: str | None = None
    rabbitmq_message_id: str | None = None

    @property
    def attempt_count(self) -> int:
        return self.attempts

    def to_envelope(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "scope_type": self.scope_type,
            "scope_key": self.scope_key,
            "source_version": self.source_version,
            "priority": self.priority,
            "trace_id": self.trace_id,
        }


class RuntimeQueueDataError(ValueError):
    pass


class _DeferEventDedupeCollision(RuntimeError):
    pass


def _is_unique_violation_error(exc: Exception) -> bool:
    return getattr(exc, "sqlstate", None) == "23505" or exc.__class__.__name__ == "UniqueViolation"


@dataclass(frozen=True)
class RuntimeQueueSettings:
    backend: str = "postgres"
    rabbitmq_url: str | None = None
    rabbitmq_vhost: str | None = None
    rabbitmq_exchange: str = "finops.events"
    rabbitmq_queue_prefix: str = "finops"
    rabbitmq_workbench_queue: str = "finops.workbench.read_model.refresh"
    rabbitmq_workbench_routing_key: str = "workbench.read_model.refresh"
    rabbitmq_dead_letter_exchange: str = "finops.events.dlx"
    rabbitmq_workbench_dead_letter_queue: str = "finops.workbench.read_model.refresh.dlq"
    rabbitmq_prefetch: int = 10
    rabbitmq_publish_confirm: bool = True
    rabbitmq_heartbeat_seconds: int = 60
    rabbitmq_consumer_postgres_drain_interval_seconds: float = 0.05
    rabbitmq_blocked_connection_timeout_seconds: int = 300
    rabbitmq_management_url: str | None = None
    rabbitmq_management_username: str | None = None
    rabbitmq_management_password: str | None = None
    rabbitmq_management_timeout_seconds: int = 2
    rabbitmq_shadow_publish: bool = False
    rabbitmq_dispatch_event_types: tuple[str, ...] = DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> RuntimeQueueSettings:
        source = os.environ if env is None else env
        backend = str(source.get("FIN_OPS_QUEUE_BACKEND") or "postgres").strip().lower() or "postgres"
        if backend not in {"postgres", "rabbitmq"}:
            raise RuntimeQueueDataError("FIN_OPS_QUEUE_BACKEND must be postgres or rabbitmq.")
        return cls(
            backend=backend,
            rabbitmq_url=str(source.get("RABBITMQ_URL") or "").strip() or None,
            rabbitmq_vhost=str(source.get("RABBITMQ_VHOST") or "").strip() or None,
            rabbitmq_exchange=str(source.get("RABBITMQ_EXCHANGE") or "finops.events").strip() or "finops.events",
            rabbitmq_queue_prefix=str(source.get("RABBITMQ_QUEUE_PREFIX") or "finops").strip().rstrip(".") or "finops",
            rabbitmq_workbench_queue=str(source.get("RABBITMQ_WORKBENCH_QUEUE") or "finops.workbench.read_model.refresh").strip()
            or "finops.workbench.read_model.refresh",
            rabbitmq_workbench_routing_key=str(source.get("RABBITMQ_WORKBENCH_ROUTING_KEY") or "workbench.read_model.refresh").strip()
            or "workbench.read_model.refresh",
            rabbitmq_dead_letter_exchange=str(source.get("RABBITMQ_DEAD_LETTER_EXCHANGE") or "finops.events.dlx").strip()
            or "finops.events.dlx",
            rabbitmq_workbench_dead_letter_queue=str(
                source.get("RABBITMQ_WORKBENCH_DEAD_LETTER_QUEUE") or "finops.workbench.read_model.refresh.dlq"
            ).strip()
            or "finops.workbench.read_model.refresh.dlq",
            rabbitmq_prefetch=_positive_int(source.get("RABBITMQ_PREFETCH"), default=10, name="RABBITMQ_PREFETCH"),
            rabbitmq_publish_confirm=_bool(source.get("RABBITMQ_PUBLISH_CONFIRM"), default=True),
            rabbitmq_heartbeat_seconds=_positive_int(source.get("RABBITMQ_HEARTBEAT_SECONDS"), default=60, name="RABBITMQ_HEARTBEAT_SECONDS"),
            rabbitmq_consumer_postgres_drain_interval_seconds=_positive_float(
                source.get("RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS"),
                default=0.05,
                name="RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS",
            ),
            rabbitmq_blocked_connection_timeout_seconds=_positive_int(
                source.get("RABBITMQ_BLOCKED_CONNECTION_TIMEOUT_SECONDS"),
                default=300,
                name="RABBITMQ_BLOCKED_CONNECTION_TIMEOUT_SECONDS",
            ),
            rabbitmq_management_url=str(source.get("RABBITMQ_MANAGEMENT_URL") or "").strip() or None,
            rabbitmq_management_username=str(source.get("RABBITMQ_MANAGEMENT_USERNAME") or "").strip() or None,
            rabbitmq_management_password=str(source.get("RABBITMQ_MANAGEMENT_PASSWORD") or "").strip() or None,
            rabbitmq_management_timeout_seconds=_positive_int(
                source.get("RABBITMQ_MANAGEMENT_TIMEOUT_SECONDS"),
                default=2,
                name="RABBITMQ_MANAGEMENT_TIMEOUT_SECONDS",
            ),
            rabbitmq_shadow_publish=_bool(source.get("RABBITMQ_SHADOW_PUBLISH"), default=False),
            rabbitmq_dispatch_event_types=_event_type_tuple(
                source.get("RABBITMQ_DISPATCH_EVENT_TYPES"),
                default=DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES,
                name="RABBITMQ_DISPATCH_EVENT_TYPES",
            ),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "queue_backend": self.backend,
            "rabbitmq_configured": bool(self.rabbitmq_url),
            "rabbitmq_vhost": self.rabbitmq_vhost,
            "rabbitmq_exchange": self.rabbitmq_exchange,
            "rabbitmq_queue_prefix": self.rabbitmq_queue_prefix,
            "rabbitmq_workbench_queue": self.rabbitmq_workbench_queue,
            "rabbitmq_workbench_routing_key": self.rabbitmq_workbench_routing_key,
            "rabbitmq_dead_letter_exchange": self.rabbitmq_dead_letter_exchange,
            "rabbitmq_workbench_dead_letter_queue": self.rabbitmq_workbench_dead_letter_queue,
            "rabbitmq_prefetch": self.rabbitmq_prefetch,
            "rabbitmq_publish_confirm": self.rabbitmq_publish_confirm,
            "rabbitmq_heartbeat_seconds": self.rabbitmq_heartbeat_seconds,
            "rabbitmq_consumer_postgres_drain_interval_seconds": self.rabbitmq_consumer_postgres_drain_interval_seconds,
            "rabbitmq_blocked_connection_timeout_seconds": self.rabbitmq_blocked_connection_timeout_seconds,
            "rabbitmq_management_configured": bool(self.rabbitmq_management_url),
            "rabbitmq_shadow_publish": self.rabbitmq_shadow_publish,
            "rabbitmq_dispatch_event_types": list(self.rabbitmq_dispatch_event_types),
        }


class RuntimeQueueRepository:
    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        scope_type: str | None = None,
        scope_key: str | None = None,
        dedupe_key: str | None = None,
        payload: dict[str, Any] | None = None,
        tenant_id: str = "default",
        available_at: Any | None = None,
        source_version: int | str | None = None,
        priority: str = "normal",
        trace_id: str | None = None,
    ) -> RuntimeQueueEvent:
        normalized_source_version = _optional_int(source_version)
        normalized_priority = _normalize_priority(priority)
        normalized_trace_id = str(trace_id or "").strip() or None
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                insert into job.outbox_events (
                    tenant_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    scope_type,
                    scope_key,
                    dedupe_key,
                    payload,
                    available_at,
                    schema_version,
                    source_version,
                    priority,
                    trace_id
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), 1, %s, %s, %s)
                on conflict (tenant_id, dedupe_key)
                where dedupe_key is not null and status = 'pending'
                do update set updated_at = job.outbox_events.updated_at
                returning
                    id::text as event_id,
                    tenant_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    scope_type,
                    scope_key,
                    dedupe_key,
                    payload,
                    attempts,
                    status,
                    schema_version,
                    source_version,
                    priority,
                    trace_id
                """,
                (
                    tenant_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    scope_type,
                    scope_key,
                    dedupe_key,
                    self._json_param(payload or {}),
                    available_at,
                    normalized_source_version,
                    normalized_priority,
                    normalized_trace_id,
                ),
            )
            if row is None:
                raise RuntimeError("Runtime queue enqueue did not return an event.")
            return _event_from_row(row)

    def enqueue_read_model_refresh(
        self,
        *,
        scope_type: str,
        scope_key: str,
        reason: str,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RuntimeQueueEvent:
        with self._connection.transaction() as transaction:
            return self.enqueue_read_model_refresh_in_transaction(
                transaction=transaction,
                scope_type=scope_type,
                scope_key=scope_key,
                reason=reason,
                tenant_id=tenant_id,
                priority=priority,
                trace_id=trace_id,
                metadata=metadata,
            )

    def enqueue_read_model_refreshes_in_transaction(
        self,
        *,
        transaction: Any,
        refreshes: Iterable[dict[str, object]],
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
    ) -> list[RuntimeQueueEvent]:
        normalized_tenant_id = str(tenant_id or "default").strip() or "default"
        normalized_priority = _normalize_priority(priority)
        normalized_trace_id = str(trace_id or "").strip() or None
        rows: list[tuple[object, ...]] = []
        seen_dedupe_keys: set[str] = set()
        for item in list(refreshes or []):
            if not isinstance(item, dict):
                continue
            normalized_scope_type = str(item.get("scope_type") or "").strip()
            normalized_scope_key = str(item.get("scope_key") or "").strip()
            normalized_reason = str(item.get("reason") or "").strip() or "read_model_refresh"
            if not normalized_scope_type or not normalized_scope_key:
                raise RuntimeQueueDataError("scope_type and scope_key are required for read model refresh.")
            metadata_payload = _safe_read_model_refresh_metadata(
                item.get("metadata") if isinstance(item.get("metadata"), dict) else None
            )
            payload = {
                "scope_type": normalized_scope_type,
                "scope_key": normalized_scope_key,
                "reason": normalized_reason,
                **({"metadata": metadata_payload} if metadata_payload else {}),
                **({"action_name": metadata_payload["action_name"]} if metadata_payload.get("action_name") else {}),
            }
            event_type = f"{normalized_scope_type}.read_model.refresh"
            dedupe_key = f"{event_type}:{normalized_scope_type}:{normalized_scope_key}"
            if dedupe_key in seen_dedupe_keys:
                continue
            seen_dedupe_keys.add(dedupe_key)
            rows.append(
                (
                    len(rows),
                    normalized_tenant_id,
                    normalized_scope_type,
                    normalized_scope_key,
                    normalized_reason,
                    normalized_priority,
                    normalized_trace_id,
                    self._json_param(payload),
                    event_type,
                    dedupe_key,
                )
            )
        if not rows:
            return []

        value_sql = ", ".join(["(%s::integer, %s::text, %s::text, %s::text, %s::text, %s::text, %s::text, %s::jsonb, %s::text, %s::text)"] * len(rows))
        params = tuple(value for row in rows for value in row)
        event_rows = transaction.fetch_all(
            f"""
            with input(
                ord, tenant_id, scope_type, scope_key, reason, priority, trace_id,
                payload, event_type, dedupe_key
            ) as (
                values {value_sql}
            ),
            dirty as (
                insert into job.read_model_dirty_scopes(
                    tenant_id, scope_type, scope_key, reason, payload, raw_payload,
                    source_version, status, next_run_at, priority, trace_id
                )
                select
                    input.tenant_id,
                    input.scope_type,
                    input.scope_key,
                    input.reason,
                    input.payload,
                    input.payload,
                    coalesce((
                        select max(existing.source_version) + 1
                        from job.read_model_dirty_scopes existing
                        where existing.tenant_id = input.tenant_id
                          and existing.scope_type = input.scope_type
                          and existing.scope_key = input.scope_key
                    ), 0),
                    'pending',
                    clock_timestamp(),
                    input.priority,
                    input.trace_id
                from input
            on conflict (tenant_id, scope_type, scope_key)
            where status in ('pending', 'processing')
            do update set
                reason = excluded.reason,
                payload = {_merge_refresh_payload_sql("job.read_model_dirty_scopes.payload", "excluded.payload")},
                raw_payload = {_merge_refresh_payload_sql("job.read_model_dirty_scopes.raw_payload", "excluded.raw_payload")},
                source_version = job.read_model_dirty_scopes.source_version + 1,
                status = 'pending',
                next_run_at = clock_timestamp(),
                    priority = excluded.priority,
                    trace_id = coalesce(excluded.trace_id, job.read_model_dirty_scopes.trace_id),
                    updated_at = clock_timestamp()
                returning tenant_id, scope_type, scope_key, source_version
            ),
            event_rows as (
                insert into job.outbox_events (
                    tenant_id, event_type, aggregate_type, aggregate_id,
                    scope_type, scope_key, dedupe_key, schema_version,
                    source_version, priority, trace_id, payload, raw_payload,
                    available_at, created_at, updated_at, next_publish_at
                )
                select
                    input.tenant_id,
                    input.event_type,
                    'read_model',
                    input.scope_key,
                    input.scope_type,
                    input.scope_key,
                    input.dedupe_key,
                    1,
                    dirty.source_version,
                    input.priority,
                    input.trace_id,
                    input.payload || jsonb_build_object('source_version', dirty.source_version),
                    input.payload || jsonb_build_object('source_version', dirty.source_version),
                    clock_timestamp(),
                    clock_timestamp(),
                    clock_timestamp(),
                    clock_timestamp()
                from input
                join dirty
                  on dirty.tenant_id = input.tenant_id
                 and dirty.scope_type = input.scope_type
                 and dirty.scope_key = input.scope_key
            on conflict (tenant_id, dedupe_key)
            where dedupe_key is not null and status = 'pending'
            do update set
                    payload = {_merge_refresh_payload_sql("job.outbox_events.payload", "excluded.payload")},
                    raw_payload = {_merge_refresh_payload_sql("job.outbox_events.raw_payload", "excluded.raw_payload")},
                    source_version = excluded.source_version,
                    priority = excluded.priority,
                    available_at = least(job.outbox_events.available_at, excluded.available_at),
                    trace_id = coalesce(excluded.trace_id, job.outbox_events.trace_id),
                    publish_status = 'unpublished',
                    published_at = null,
                    publish_last_error = null,
                    next_publish_at = clock_timestamp(),
                    publish_locked_by = null,
                    publish_locked_at = null,
                    publish_confirmed_at = null,
                    created_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                returning
                    id::text as event_id,
                    tenant_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    scope_type,
                    scope_key,
                    dedupe_key,
                    payload,
                    attempts,
                    status,
                    schema_version,
                    source_version,
                    priority,
                    trace_id
            )
            select event_rows.*
            from event_rows
            join input
              on input.tenant_id = event_rows.tenant_id
             and input.dedupe_key = event_rows.dedupe_key
            order by input.ord
            """,
            params,
        )
        return [_event_from_row(row) for row in event_rows]

    def enqueue_read_model_refresh_in_transaction(
        self,
        *,
        transaction: Any,
        scope_type: str,
        scope_key: str,
        reason: str,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RuntimeQueueEvent:
        normalized_scope_type = str(scope_type or "").strip()
        normalized_scope_key = str(scope_key or "").strip()
        normalized_reason = str(reason or "").strip() or "read_model_refresh"
        normalized_priority = _normalize_priority(priority)
        normalized_trace_id = str(trace_id or "").strip() or None
        if not normalized_scope_type or not normalized_scope_key:
            raise RuntimeQueueDataError("scope_type and scope_key are required for read model refresh.")
        metadata_payload = _safe_read_model_refresh_metadata(metadata)
        payload = {
            "scope_type": normalized_scope_type,
            "scope_key": normalized_scope_key,
            "reason": normalized_reason,
            **({"metadata": metadata_payload} if metadata_payload else {}),
            **({"action_name": metadata_payload["action_name"]} if metadata_payload.get("action_name") else {}),
        }
        event_type = f"{normalized_scope_type}.read_model.refresh"
        dirty_row = transaction.fetch_one(
            f"""
            insert into job.read_model_dirty_scopes(
                tenant_id, scope_type, scope_key, reason, payload, raw_payload,
                source_version, status, next_run_at, priority, trace_id
            )
            values (
                %s, %s, %s, %s, %s, %s,
                coalesce((
                    select max(existing.source_version) + 1
                    from job.read_model_dirty_scopes existing
                    where existing.tenant_id = %s
                      and existing.scope_type = %s
                      and existing.scope_key = %s
                ), 0),
                'pending',
                clock_timestamp(),
                %s,
                %s
            )
            on conflict (tenant_id, scope_type, scope_key)
            where status in ('pending', 'processing')
            do update set
                reason = excluded.reason,
                payload = {_merge_refresh_payload_sql("job.read_model_dirty_scopes.payload", "excluded.payload")},
                raw_payload = {_merge_refresh_payload_sql("job.read_model_dirty_scopes.raw_payload", "excluded.raw_payload")},
                source_version = job.read_model_dirty_scopes.source_version + 1,
                status = 'pending',
                next_run_at = clock_timestamp(),
                priority = excluded.priority,
                trace_id = coalesce(excluded.trace_id, job.read_model_dirty_scopes.trace_id),
                updated_at = clock_timestamp()
            returning source_version
            """,
            (
                tenant_id,
                normalized_scope_type,
                normalized_scope_key,
                normalized_reason,
                self._json_param(payload),
                self._json_param(payload),
                tenant_id,
                normalized_scope_type,
                normalized_scope_key,
                normalized_priority,
                normalized_trace_id,
            ),
        )
        source_version = int((dirty_row or {}).get("source_version") or 0)
        payload = {**payload, "source_version": source_version}
        row = transaction.fetch_one(
            f"""
            insert into job.outbox_events (
                tenant_id, event_type, aggregate_type, aggregate_id,
                scope_type, scope_key, dedupe_key, schema_version,
                source_version, priority, trace_id, payload, raw_payload,
                available_at, created_at, updated_at, next_publish_at
            )
            values (
                %s, %s, 'read_model', %s, %s, %s, %s, 1, %s, %s, %s, %s, %s,
                clock_timestamp(), clock_timestamp(), clock_timestamp(), clock_timestamp()
            )
            on conflict (tenant_id, dedupe_key)
            where dedupe_key is not null and status = 'pending'
            do update set
                payload = {_merge_refresh_payload_sql("job.outbox_events.payload", "excluded.payload")},
                raw_payload = {_merge_refresh_payload_sql("job.outbox_events.raw_payload", "excluded.raw_payload")},
                source_version = excluded.source_version,
                priority = excluded.priority,
                available_at = least(job.outbox_events.available_at, excluded.available_at),
                trace_id = coalesce(excluded.trace_id, job.outbox_events.trace_id),
                publish_status = 'unpublished',
                published_at = null,
                publish_last_error = null,
                next_publish_at = clock_timestamp(),
                publish_locked_by = null,
                publish_locked_at = null,
                publish_confirmed_at = null,
                created_at = clock_timestamp(),
                updated_at = clock_timestamp()
            returning
                id::text as event_id,
                tenant_id,
                event_type,
                aggregate_type,
                aggregate_id,
                scope_type,
                scope_key,
                dedupe_key,
                payload,
                attempts,
                status,
                schema_version,
                source_version,
                priority,
                trace_id
            """,
            (
                tenant_id,
                event_type,
                normalized_scope_key,
                normalized_scope_type,
                normalized_scope_key,
                f"{event_type}:{normalized_scope_type}:{normalized_scope_key}",
                source_version,
                normalized_priority,
                normalized_trace_id,
                self._json_param(payload),
                self._json_param(payload),
            ),
        )
        if row is None:
            raise RuntimeError("Runtime queue enqueue did not return a read model refresh event.")
        return _event_from_row(row)

    def claim_next(
        self,
        worker_id: str,
        event_types: Iterable[str] | None = None,
        lock_timeout_seconds: int = 300,
        scope_keys: Iterable[str] | None = None,
        exclude_scope_keys: Iterable[str] | None = None,
    ) -> RuntimeQueueEvent | None:
        event_type_list = list(event_types or [])
        event_type_filter = ""
        scope_key_list = _normalized_scope_key_list(scope_keys)
        excluded_scope_key_list = _normalized_scope_key_list(exclude_scope_keys)
        scope_key_filter = ""
        excluded_scope_key_filter = ""
        params_list: list[Any] = [worker_id, lock_timeout_seconds]
        if event_type_list:
            event_type_filter = "and event_type = any(%s)"
            params_list.append(event_type_list)
        if scope_key_list:
            scope_key_filter = "and scope_key = any(%s)"
            params_list.append(scope_key_list)
        if excluded_scope_key_list:
            excluded_scope_key_filter = "and not (scope_key = any(%s))"
            params_list.append(excluded_scope_key_list)
        params = tuple(params_list)

        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                f"""
                update job.outbox_events
                set
                    status = 'processing',
                    locked_by = %s,
                    locked_at = now(),
                    updated_at = now(),
                    attempts = attempts + 1
                from (
                    select id
                    from job.outbox_events
                    where (
                        (status = 'pending' and available_at <= now())
                        or (
                            status = 'processing'
                            and available_at <= now()
                            and locked_at < now() - (%s * interval '1 second')
                        )
                    )
                      {event_type_filter}
                      {scope_key_filter}
                      {excluded_scope_key_filter}
                    order by
                        case priority
                            when 'urgent' then 3
                            when 'high' then 2
                            when 'normal' then 1
                            else 0
                        end desc,
                        available_at,
                        created_at,
                        id
                    limit 1
                    for update skip locked
                ) candidate
                where job.outbox_events.id = candidate.id
                returning
                    job.outbox_events.id::text as event_id,
                    job.outbox_events.tenant_id,
                    job.outbox_events.event_type,
                    job.outbox_events.aggregate_type,
                    job.outbox_events.aggregate_id,
                    job.outbox_events.scope_type,
                    job.outbox_events.scope_key,
                    job.outbox_events.dedupe_key,
                    job.outbox_events.payload,
                    job.outbox_events.attempts,
                    job.outbox_events.status,
                    job.outbox_events.schema_version,
                    job.outbox_events.source_version,
                    job.outbox_events.priority,
                    job.outbox_events.trace_id
                """,
                params,
            )
            return _event_from_row(row) if row is not None else None

    def claim_events(
        self,
        *,
        worker_id: str,
        event_types: Iterable[str] | None = None,
        lock_timeout_seconds: int = 300,
        limit: int = 1,
        scope_keys: Iterable[str] | None = None,
        exclude_scope_keys: Iterable[str] | None = None,
    ) -> list[RuntimeQueueEvent]:
        normalized_limit = max(1, int(limit))
        claimed: list[RuntimeQueueEvent] = []
        for _ in range(normalized_limit):
            event = self.claim_next(
                worker_id,
                event_types=event_types,
                lock_timeout_seconds=lock_timeout_seconds,
                scope_keys=scope_keys,
                exclude_scope_keys=exclude_scope_keys,
            )
            if event is None:
                break
            claimed.append(event)
        return claimed

    def get_event(self, event_id: str) -> RuntimeQueueEvent | None:
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                select
                    id::text as event_id,
                    tenant_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    scope_type,
                    scope_key,
                    dedupe_key,
                    payload,
                    attempts,
                    status,
                    schema_version,
                    source_version,
                    priority,
                    trace_id,
                    publish_status,
                    publish_attempt_count,
                    rabbitmq_exchange,
                    rabbitmq_routing_key,
                    rabbitmq_message_id
                from job.outbox_events
                where id = %s
                """,
                (event_id,),
            )
        return _event_from_row(row) if row is not None else None

    def claim_event_by_id(
        self,
        *,
        event_id: str,
        worker_id: str,
        event_types: Iterable[str] | None = None,
        lock_timeout_seconds: int = 300,
        scope_keys: Iterable[str] | None = None,
        exclude_scope_keys: Iterable[str] | None = None,
    ) -> RuntimeQueueEvent | None:
        event_type_list = list(event_types or [])
        event_type_filter = ""
        scope_key_list = _normalized_scope_key_list(scope_keys)
        excluded_scope_key_list = _normalized_scope_key_list(exclude_scope_keys)
        scope_key_filter = ""
        excluded_scope_key_filter = ""
        params_list: list[Any] = [worker_id, event_id, lock_timeout_seconds]
        if event_type_list:
            event_type_filter = "and event_type = any(%s)"
            params_list.append(event_type_list)
        if scope_key_list:
            scope_key_filter = "and scope_key = any(%s)"
            params_list.append(scope_key_list)
        if excluded_scope_key_list:
            excluded_scope_key_filter = "and not (scope_key = any(%s))"
            params_list.append(excluded_scope_key_list)
        params = tuple(params_list)

        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                f"""
                update job.outbox_events
                set
                    status = 'processing',
                    locked_by = %s,
                    locked_at = now(),
                    updated_at = now(),
                    attempts = attempts + 1
                where id = %s
                  and (
                      (status = 'pending' and available_at <= now())
                      or (
                          status = 'processing'
                          and available_at <= now()
                          and locked_at < now() - (%s * interval '1 second')
                      )
                  )
                  {event_type_filter}
                  {scope_key_filter}
                  {excluded_scope_key_filter}
                returning
                    id::text as event_id,
                    tenant_id,
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    scope_type,
                    scope_key,
                    dedupe_key,
                    payload,
                    attempts,
                    status,
                    schema_version,
                    source_version,
                    priority,
                    trace_id,
                    publish_status,
                    publish_attempt_count,
                    rabbitmq_exchange,
                    rabbitmq_routing_key,
                    rabbitmq_message_id
                """,
                params,
            )
        return _event_from_row(row) if row is not None else None

    def claim_publishable_events(
        self,
        *,
        publisher_id: str,
        event_types: Iterable[str] | None = None,
        lock_timeout_seconds: int = 300,
        limit: int = 100,
    ) -> list[RuntimeQueueEvent]:
        normalized_limit = max(1, int(limit))
        event_type_list = list(event_types or [])
        event_type_filter = ""
        params: tuple[Any, ...]
        if event_type_list:
            event_type_filter = "and event_type = any(%s)"
            params = (publisher_id, lock_timeout_seconds, event_type_list, normalized_limit)
        else:
            params = (publisher_id, lock_timeout_seconds, normalized_limit)

        with self._connection.transaction() as transaction:
            rows = transaction.fetch_all(
                f"""
                update job.outbox_events
                set
                    publish_status = 'publishing',
                    publish_locked_by = %s,
                    publish_locked_at = now(),
                    publish_attempt_count = publish_attempt_count + 1,
                    publish_last_error = null,
                    updated_at = now()
                from (
                    select id
                    from job.outbox_events
                    where status = 'pending'
                      and available_at <= now()
                      and next_publish_at <= now()
                      and (
                          publish_status in ('unpublished', 'failed')
                          or (
                              publish_status = 'publishing'
                              and publish_locked_at < now() - (%s * interval '1 second')
                          )
                      )
                      {event_type_filter}
                    order by
                        case priority
                            when 'urgent' then 3
                            when 'high' then 2
                            when 'normal' then 1
                            else 0
                        end desc,
                        next_publish_at,
                        available_at,
                        created_at,
                        id
                    limit %s
                    for update skip locked
                ) candidate
                where job.outbox_events.id = candidate.id
                returning
                    job.outbox_events.id::text as event_id,
                    job.outbox_events.tenant_id,
                    job.outbox_events.event_type,
                    job.outbox_events.aggregate_type,
                    job.outbox_events.aggregate_id,
                    job.outbox_events.scope_type,
                    job.outbox_events.scope_key,
                    job.outbox_events.dedupe_key,
                    job.outbox_events.payload,
                    job.outbox_events.attempts,
                    job.outbox_events.status,
                    job.outbox_events.schema_version,
                    job.outbox_events.source_version,
                    job.outbox_events.priority,
                    job.outbox_events.trace_id,
                    job.outbox_events.publish_status,
                    job.outbox_events.publish_attempt_count,
                    job.outbox_events.rabbitmq_exchange,
                    job.outbox_events.rabbitmq_routing_key,
                    job.outbox_events.rabbitmq_message_id
                """,
                params,
            )
        return [_event_from_row(row) for row in rows]

    def mark_published(
        self,
        event_id: str,
        *,
        publisher_id: str,
        exchange: str,
        routing_key: str,
        message_id: str,
        confirm_latency_ms: float | None = None,
    ) -> bool:
        result_payload = {
            "exchange": exchange,
            "routing_key": routing_key,
            "message_id": message_id,
        }
        if confirm_latency_ms is not None:
            result_payload["confirm_latency_ms"] = round(float(confirm_latency_ms), 3)
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    publish_status = 'published',
                    published_at = now(),
                    publish_confirmed_at = now(),
                    publish_last_error = null,
                    publish_locked_by = null,
                    publish_locked_at = null,
                    rabbitmq_exchange = %s,
                    rabbitmq_routing_key = %s,
                    rabbitmq_message_id = %s,
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{rabbitmq_publish}',
                        %s::jsonb,
                        true
                    )
                where id = %s
                  and publish_status = 'publishing'
                  and publish_locked_by = %s
                returning id
                """,
                (exchange, routing_key, message_id, self._json_param(result_payload), event_id, publisher_id),
            )
        return row is not None

    def mark_publish_failed(
        self,
        event_id: str,
        *,
        publisher_id: str,
        error: str,
        retry_delay_seconds: int = 60,
    ) -> bool:
        normalized_error = str(error or "").strip() or "rabbitmq_publish_failed"
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    publish_status = 'failed',
                    publish_last_error = %s,
                    next_publish_at = now() + (%s * interval '1 second'),
                    publish_locked_by = null,
                    publish_locked_at = null,
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{rabbitmq_publish_failure}',
                        jsonb_build_object('error', %s::text, 'retry_delay_seconds', %s::integer),
                        true
                    )
                where id = %s
                  and publish_status = 'publishing'
                  and publish_locked_by = %s
                returning id
                """,
                (normalized_error, retry_delay_seconds, normalized_error, retry_delay_seconds, event_id, publisher_id),
            )
        return row is not None

    def reset_publish_state(self, event_id: str, *, reason: str = "manual_republish") -> bool:
        normalized_reason = str(reason or "").strip() or "manual_republish"
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    publish_status = 'unpublished',
                    published_at = null,
                    publish_last_error = null,
                    next_publish_at = now(),
                    publish_locked_by = null,
                    publish_locked_at = null,
                    rabbitmq_exchange = null,
                    rabbitmq_routing_key = null,
                    rabbitmq_message_id = null,
                    publish_confirmed_at = null,
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{rabbitmq_republish}',
                        jsonb_build_object('reason', %s, 'requested_at', now()),
                        true
                    )
                where id = %s
                  and status = 'pending'
                returning id
                """,
                (normalized_reason, event_id),
            )
        return row is not None

    def runtime_control_status(self) -> dict[str, Any]:
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                select settings_payload
                from app.app_settings
                where settings_key = 'runtime:rabbitmq_control'
                """
            )
        payload = (row or {}).get("settings_payload") if row else {}
        return payload if isinstance(payload, dict) else {}

    def is_runtime_control_paused(self, component: str) -> bool:
        key = f"{str(component or '').strip()}_paused"
        return bool(self.runtime_control_status().get(key))

    def ack_event(self, event_id: str, worker_id: str, result_payload: dict[str, Any] | None = None) -> bool:
        return self.complete(event_id, worker_id, result_payload=result_payload)

    def complete(self, event_id: str, worker_id: str, result_payload: dict[str, Any] | None = None) -> bool:
        if result_payload is None:
            sql = """
                update job.outbox_events
                set
                    status = 'done',
                    processed_at = now(),
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
            """
            params = (event_id, worker_id)
        else:
            sql = """
                update job.outbox_events
                set
                    status = 'done',
                    processed_at = now(),
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null,
                    raw_payload = jsonb_set(coalesce(raw_payload, '{}'::jsonb), '{runtime_result}', %s::jsonb, true)
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
            """
            params = (self._json_param(result_payload), event_id, worker_id)

        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(sql, params)
        return row is not None

    def fail(
        self,
        event_id: str,
        worker_id: str,
        error: str,
        retry: bool = True,
        retry_delay_seconds: int = 60,
    ) -> bool:
        if retry:
            sql = """
                update job.outbox_events
                set
                    status = 'pending',
                    last_error = %s,
                    available_at = now() + (%s * interval '1 second'),
                    publish_status = 'unpublished',
                    publish_last_error = null,
                    next_publish_at = now() + (%s * interval '1 second'),
                    publish_locked_by = null,
                    publish_locked_at = null,
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
            """
            params = (error, retry_delay_seconds, retry_delay_seconds, event_id, worker_id)
        else:
            sql = """
                update job.outbox_events
                set
                    status = 'failed',
                    last_error = %s,
                    processed_at = now(),
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
            """
            params = (error, event_id, worker_id)

        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(sql, params)
        return row is not None

    def retry(self, event_id: str, worker_id: str, error: str, retry_delay_seconds: int = 60) -> bool:
        return self.fail(
            event_id,
            worker_id,
            error,
            retry=True,
            retry_delay_seconds=retry_delay_seconds,
        )

    def fail_event(
        self,
        event_id: str,
        worker_id: str,
        error: str,
        *,
        retryable: bool = True,
        retry_delay_seconds: int = 60,
        max_attempts: int = 5,
    ) -> bool:
        if retryable:
            sql = """
                update job.outbox_events
                set
                    status = case when attempts >= %s then 'dead_lettered' else 'pending' end,
                    last_error = %s,
                    available_at = case when attempts >= %s then available_at else now() + (%s * interval '1 second') end,
                    publish_status = case when attempts >= %s then publish_status else 'unpublished' end,
                    publish_last_error = case when attempts >= %s then publish_last_error else null end,
                    next_publish_at = case when attempts >= %s then next_publish_at else now() + (%s * interval '1 second') end,
                    publish_locked_by = null,
                    publish_locked_at = null,
                    processed_at = case when attempts >= %s then now() else processed_at end,
                    dead_lettered_at = case when attempts >= %s then now() else dead_lettered_at end,
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null,
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{runtime_failure}',
                        jsonb_build_object('error', %s::text, 'retryable', true, 'max_attempts', %s::integer),
                        true
                    )
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
            """
            params = (
                max_attempts,
                error,
                max_attempts,
                retry_delay_seconds,
                max_attempts,
                max_attempts,
                max_attempts,
                retry_delay_seconds,
                max_attempts,
                max_attempts,
                error,
                max_attempts,
                event_id,
                worker_id,
            )
        else:
            sql = """
                update job.outbox_events
                set
                    status = 'failed',
                    last_error = %s,
                    processed_at = now(),
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null,
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{runtime_failure}',
                        jsonb_build_object('error', %s::text, 'retryable', false),
                        true
                    )
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
            """
            params = (error, error, event_id, worker_id)

        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(sql, params)
        return row is not None

    def requeue_event(self, event_id: str, *, reason: str = "manual_requeue") -> bool:
        normalized_reason = str(reason or "").strip() or "manual_requeue"
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    status = 'pending',
                    attempts = 0,
                    attempt_count = 0,
                    available_at = now(),
                    publish_status = 'unpublished',
                    published_at = null,
                    publish_last_error = null,
                    next_publish_at = now(),
                    publish_locked_by = null,
                    publish_locked_at = null,
                    rabbitmq_exchange = null,
                    rabbitmq_routing_key = null,
                    rabbitmq_message_id = null,
                    publish_confirmed_at = null,
                    last_error = null,
                    processed_at = null,
                    dead_lettered_at = null,
                    locked_by = null,
                    locked_at = null,
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{manual_requeue}',
                        jsonb_build_object('reason', %s::text, 'requeued_at', now()),
                        true
                    )
                where id = %s
                  and status in ('failed', 'dead_lettered', 'pending')
                returning id
                """,
                (normalized_reason, event_id),
            )
        return row is not None

    def release_event(self, event_id: str, worker_id: str, *, reason: str = "worker_shutdown") -> bool:
        normalized_reason = str(reason or "").strip() or "worker_shutdown"
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    status = 'pending',
                    available_at = now(),
                    locked_by = null,
                    locked_at = null,
                    attempts = greatest(coalesce(attempts, 0) - 1, 0),
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{runtime_shutdown_release}',
                        jsonb_build_object('reason', %s::text, 'released_at', now()),
                        true
                    )
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
                """,
                (normalized_reason, event_id, worker_id),
            )
        return row is not None

    def release_stale_processing_events(
        self,
        *,
        stale_after_seconds: int,
        limit: int = 100,
        reason: str = "operator_stale_processing_release",
        event_types: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_reason = str(reason or "").strip() or "operator_stale_processing_release"
        normalized_stale_after_seconds = max(1, int(stale_after_seconds))
        normalized_limit = max(1, int(limit))
        normalized_event_types = [str(event_type).strip() for event_type in event_types or () if str(event_type).strip()]
        event_type_filter = ""
        params: tuple[Any, ...]
        if normalized_event_types:
            event_type_filter = "and stale.event_type = any(%s)"
            params = (
                normalized_stale_after_seconds,
                normalized_event_types,
                normalized_limit,
                normalized_reason,
                normalized_stale_after_seconds,
            )
        else:
            params = (
                normalized_stale_after_seconds,
                normalized_limit,
                normalized_reason,
                normalized_stale_after_seconds,
            )

        with self._connection.transaction() as transaction:
            rows = transaction.fetch_all(
                f"""
                with ranked as (
                    select
                        stale.id,
                        row_number() over (
                            partition by stale.tenant_id, coalesce(stale.dedupe_key, stale.id::text)
                            order by coalesce(stale.source_version, 0) desc, stale.created_at desc, stale.id desc
                        ) as dedupe_rank,
                        stale.locked_at,
                        stale.created_at
                    from job.outbox_events stale
                    where stale.status = 'processing'
                      and stale.locked_at < now() - (%s * interval '1 second')
                      {event_type_filter}
                      and not exists (
                          select 1
                          from job.outbox_events pending
                          where pending.tenant_id = stale.tenant_id
                            and pending.dedupe_key = stale.dedupe_key
                            and pending.status = 'pending'
                            and stale.dedupe_key is not null
                      )
                ),
                candidate_ids as (
                    select id
                    from ranked
                    where dedupe_rank = 1
                    order by locked_at nulls first, created_at, id
                    limit %s
                ),
                candidates as (
                    select stale.id, stale.locked_by, stale.locked_at
                    from job.outbox_events stale
                    join candidate_ids on candidate_ids.id = stale.id
                    for update skip locked
                )
                update job.outbox_events event
                set
                    status = 'pending',
                    available_at = now(),
                    publish_status = 'unpublished',
                    published_at = null,
                    publish_last_error = null,
                    next_publish_at = now(),
                    publish_locked_by = null,
                    publish_locked_at = null,
                    rabbitmq_exchange = null,
                    rabbitmq_routing_key = null,
                    rabbitmq_message_id = null,
                    publish_confirmed_at = null,
                    locked_by = null,
                    locked_at = null,
                    attempts = greatest(coalesce(event.attempts, 0) - 1, 0),
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(event.raw_payload, '{{}}'::jsonb),
                        '{{operator_stale_processing_release}}',
                        jsonb_build_object(
                            'reason', %s::text,
                            'released_at', now(),
                            'stale_after_seconds', %s::integer,
                            'previous_locked_by', candidates.locked_by,
                            'previous_locked_at', candidates.locked_at
                        ),
                        true
                    )
                from candidates
                where event.id = candidates.id
                returning
                    event.id::text as event_id,
                    event.event_type,
                    event.scope_type,
                    event.scope_key,
                    event.dedupe_key,
                    event.status,
                    event.attempts,
                    event.priority,
                    event.source_version
                """,
                params,
            )
        return list(rows)

    def resolve_superseded_processing_events(
        self,
        *,
        stale_after_seconds: int,
        limit: int = 100,
        reason: str = "operator_superseded_processing_resolution",
        event_types: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_reason = str(reason or "").strip() or "operator_superseded_processing_resolution"
        normalized_stale_after_seconds = max(1, int(stale_after_seconds))
        normalized_limit = max(1, int(limit))
        normalized_event_types = [str(event_type).strip() for event_type in event_types or () if str(event_type).strip()]
        event_type_filter = ""
        params: tuple[Any, ...]
        if normalized_event_types:
            event_type_filter = "and stale.event_type = any(%s)"
            params = (
                normalized_stale_after_seconds,
                normalized_event_types,
                normalized_limit,
                normalized_reason,
                normalized_stale_after_seconds,
            )
        else:
            params = (
                normalized_stale_after_seconds,
                normalized_limit,
                normalized_reason,
                normalized_stale_after_seconds,
            )

        with self._connection.transaction() as transaction:
            rows = transaction.fetch_all(
                f"""
                with candidates as (
                    select
                        stale.id,
                        stale.locked_by,
                        stale.locked_at,
                        cover.id as covered_by_event_id,
                        cover.status as covered_by_status,
                        cover.source_version as covered_by_source_version
                    from job.outbox_events stale
                    join lateral (
                        select newer.id, newer.status, newer.source_version
                        from job.outbox_events newer
                        where newer.tenant_id = stale.tenant_id
                          and newer.dedupe_key = stale.dedupe_key
                          and newer.id <> stale.id
                          and newer.status in ('pending', 'processing', 'done')
                          and stale.dedupe_key is not null
                          and coalesce(newer.source_version, 0) >= coalesce(stale.source_version, 0)
                          and (
                              newer.created_at > stale.created_at
                              or (newer.created_at = stale.created_at and newer.id > stale.id)
                          )
                        order by coalesce(newer.source_version, 0) desc, newer.created_at desc, newer.id desc
                        limit 1
                    ) cover on true
                    where stale.status = 'processing'
                      and stale.locked_at < now() - (%s * interval '1 second')
                      {event_type_filter}
                    order by stale.locked_at nulls first, stale.created_at, stale.id
                    limit %s
                    for update of stale skip locked
                )
                update job.outbox_events event
                set
                    status = 'done',
                    processed_at = coalesce(event.processed_at, now()),
                    locked_by = null,
                    locked_at = null,
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(event.raw_payload, '{{}}'::jsonb),
                        '{{operator_superseded_processing_resolution}}',
                        jsonb_build_object(
                            'reason', %s::text,
                            'resolved_at', now(),
                            'stale_after_seconds', %s::integer,
                            'previous_locked_by', candidates.locked_by,
                            'previous_locked_at', candidates.locked_at,
                            'covered_by_event_id', candidates.covered_by_event_id,
                            'covered_by_status', candidates.covered_by_status,
                            'covered_by_source_version', candidates.covered_by_source_version
                        ),
                        true
                    )
                from candidates
                where event.id = candidates.id
                returning
                    event.id::text as event_id,
                    event.event_type,
                    event.scope_type,
                    event.scope_key,
                    event.dedupe_key,
                    event.status,
                    event.attempts,
                    event.priority,
                    event.source_version,
                    candidates.covered_by_event_id::text as covered_by_event_id,
                    candidates.covered_by_status,
                    candidates.covered_by_source_version
                """,
                params,
            )
        return list(rows)

    def defer_event(
        self,
        event_id: str,
        worker_id: str,
        *,
        reason: str = "dependency_not_ready",
        delay_seconds: float = 2.0,
    ) -> bool:
        normalized_reason = str(reason or "").strip() or "dependency_not_ready"
        normalized_delay_seconds = max(0.1, float(delay_seconds or 1.0))
        try:
            with self._connection.transaction() as transaction:
                return self._defer_event_in_transaction(
                    transaction,
                    event_id=event_id,
                    worker_id=worker_id,
                    normalized_reason=normalized_reason,
                    normalized_delay_seconds=normalized_delay_seconds,
                )
        except _DeferEventDedupeCollision:
            return self._resolve_defer_event_dedupe_collision(
                event_id=event_id,
                worker_id=worker_id,
                normalized_reason=normalized_reason,
                normalized_delay_seconds=normalized_delay_seconds,
            )

    def _defer_event_in_transaction(
        self,
        transaction: Any,
        *,
        event_id: str,
        worker_id: str,
        normalized_reason: str,
        normalized_delay_seconds: float,
    ) -> bool:
            target = transaction.fetch_one(
                """
                select
                    id::text as event_id,
                    tenant_id,
                    dedupe_key,
                    source_version,
                    locked_by,
                    locked_at,
                    created_at
                from job.outbox_events
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                for update
                """,
                (event_id, worker_id),
            )
            if target is None:
                return False

            cover = None
            dedupe_key = target.get("dedupe_key")
            if dedupe_key:
                cover = transaction.fetch_one(
                    """
                    select
                        id::text as event_id,
                        status,
                        source_version
                    from job.outbox_events
                    where tenant_id = %s
                      and dedupe_key = %s
                      and id <> %s
                      and status in ('pending', 'processing', 'done')
                      and coalesce(source_version, 0) >= coalesce(%s, 0)
                      and (
                          created_at > %s
                          or (created_at = %s and id > %s::uuid)
                      )
                    order by coalesce(source_version, 0) desc, created_at desc, id desc
                    limit 1
                    """,
                    (
                        target["tenant_id"],
                        dedupe_key,
                        target["event_id"],
                        target.get("source_version"),
                        target.get("created_at"),
                        target.get("created_at"),
                        target["event_id"],
                    ),
                )

            if cover is not None:
                row = transaction.fetch_one(
                    """
                    update job.outbox_events
                    set
                        status = 'done',
                        processed_at = coalesce(processed_at, now()),
                        locked_by = null,
                        locked_at = null,
                        attempts = greatest(coalesce(attempts, 0) - 1, 0),
                        updated_at = now(),
                        raw_payload = jsonb_set(
                            coalesce(raw_payload, '{}'::jsonb),
                            '{runtime_defer_superseded}',
                            jsonb_build_object(
                                'reason', %s::text,
                                'delay_seconds', %s::double precision,
                                'resolved_at', now(),
                                'previous_locked_by', %s::text,
                                'previous_locked_at', %s,
                                'covered_by_event_id', %s::text,
                                'covered_by_status', %s::text,
                                'covered_by_source_version', %s
                            ),
                            true
                        )
                    where id = %s
                      and status = 'processing'
                      and locked_by = %s
                    returning id::text as event_id
                    """,
                    (
                        normalized_reason,
                        normalized_delay_seconds,
                        target.get("locked_by"),
                        target.get("locked_at"),
                        cover.get("event_id"),
                        cover.get("status"),
                        cover.get("source_version"),
                        target["event_id"],
                        worker_id,
                    ),
                )
                return row is not None

            try:
                row = transaction.fetch_one(
                    """
                    update job.outbox_events
                    set
                        status = 'pending',
                        available_at = now() + (%s::double precision * interval '1 second'),
                        publish_status = 'unpublished',
                        publish_last_error = null,
                        next_publish_at = now() + (%s::double precision * interval '1 second'),
                        publish_locked_by = null,
                        publish_locked_at = null,
                        locked_by = null,
                        locked_at = null,
                        attempts = greatest(coalesce(attempts, 0) - 1, 0),
                        updated_at = now(),
                        raw_payload = jsonb_set(
                            coalesce(raw_payload, '{}'::jsonb),
                            '{runtime_defer}',
                            jsonb_build_object(
                                'reason', %s::text,
                                'delay_seconds', %s::double precision,
                                'deferred_at', now()
                            ),
                            true
                        )
                    where id = %s
                      and status = 'processing'
                      and locked_by = %s
                      and (
                          dedupe_key is null
                          or not exists (
                              select 1
                              from job.outbox_events newer
                              where newer.tenant_id = job.outbox_events.tenant_id
                                and newer.dedupe_key = job.outbox_events.dedupe_key
                                and newer.id <> job.outbox_events.id
                                and newer.status = 'pending'
                          )
                      )
                    returning id::text as event_id
                    """,
                    (
                        normalized_delay_seconds,
                        normalized_delay_seconds,
                        normalized_reason,
                        normalized_delay_seconds,
                        target["event_id"],
                        worker_id,
                    ),
                )
            except Exception as exc:
                if _is_unique_violation_error(exc):
                    raise _DeferEventDedupeCollision() from exc
                raise
            if row is not None:
                return True

            cover = transaction.fetch_one(
                """
                select
                    id::text as event_id,
                    status,
                    source_version
                from job.outbox_events
                where tenant_id = %s
                  and dedupe_key = %s
                  and id <> %s
                  and status in ('pending', 'processing', 'done')
                  and coalesce(source_version, 0) >= coalesce(%s, 0)
                  and (
                      created_at > %s
                      or (created_at = %s and id > %s::uuid)
                  )
                order by coalesce(source_version, 0) desc, created_at desc, id desc
                limit 1
                """,
                (
                    target["tenant_id"],
                    dedupe_key,
                    target["event_id"],
                    target.get("source_version"),
                    target.get("created_at"),
                    target.get("created_at"),
                    target["event_id"],
                ),
            )
            if cover is None:
                return False

            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    status = 'done',
                    processed_at = coalesce(processed_at, now()),
                    locked_by = null,
                    locked_at = null,
                    attempts = greatest(coalesce(attempts, 0) - 1, 0),
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{runtime_defer_superseded}',
                        jsonb_build_object(
                            'reason', %s::text,
                            'delay_seconds', %s::double precision,
                            'resolved_at', now(),
                            'previous_locked_by', %s::text,
                            'previous_locked_at', %s,
                            'covered_by_event_id', %s::text,
                            'covered_by_status', %s::text,
                            'covered_by_source_version', %s
                        ),
                        true
                    )
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id::text as event_id
                """,
                (
                    normalized_reason,
                    normalized_delay_seconds,
                    target.get("locked_by"),
                    target.get("locked_at"),
                    cover.get("event_id"),
                    cover.get("status"),
                    cover.get("source_version"),
                    target["event_id"],
                    worker_id,
                ),
            )
            return row is not None

    def _resolve_defer_event_dedupe_collision(
        self,
        *,
        event_id: str,
        worker_id: str,
        normalized_reason: str,
        normalized_delay_seconds: float,
    ) -> bool:
        with self._connection.transaction() as transaction:
            target = transaction.fetch_one(
                """
                select
                    id::text as event_id,
                    tenant_id,
                    dedupe_key,
                    source_version,
                    locked_by,
                    locked_at,
                    created_at
                from job.outbox_events
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                for update
                """,
                (event_id, worker_id),
            )
            if target is None or not target.get("dedupe_key"):
                return False
            cover = transaction.fetch_one(
                """
                select
                    id::text as event_id,
                    status,
                    source_version
                from job.outbox_events
                where tenant_id = %s
                  and dedupe_key = %s
                  and id <> %s
                  and status in ('pending', 'processing', 'done')
                  and coalesce(source_version, 0) >= coalesce(%s, 0)
                  and (
                      created_at > %s
                      or (created_at = %s and id > %s::uuid)
                  )
                order by coalesce(source_version, 0) desc, created_at desc, id desc
                limit 1
                """,
                (
                    target["tenant_id"],
                    target["dedupe_key"],
                    target["event_id"],
                    target.get("source_version"),
                    target.get("created_at"),
                    target.get("created_at"),
                    target["event_id"],
                ),
            )
            if cover is None:
                return False
            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    status = 'done',
                    processed_at = coalesce(processed_at, now()),
                    locked_by = null,
                    locked_at = null,
                    attempts = greatest(coalesce(attempts, 0) - 1, 0),
                    updated_at = now(),
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{runtime_defer_superseded}',
                        jsonb_build_object(
                            'reason', %s::text,
                            'delay_seconds', %s::double precision,
                            'resolved_at', now(),
                            'collision', true,
                            'previous_locked_by', %s::text,
                            'previous_locked_at', %s,
                            'covered_by_event_id', %s::text,
                            'covered_by_status', %s::text,
                            'covered_by_source_version', %s
                        ),
                        true
                    )
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id::text as event_id
                """,
                (
                    normalized_reason,
                    normalized_delay_seconds,
                    target.get("locked_by"),
                    target.get("locked_at"),
                    cover.get("event_id"),
                    cover.get("status"),
                    cover.get("source_version"),
                    target["event_id"],
                    worker_id,
                ),
            )
            return row is not None

    def resolve_dead_letter_event(self, event_id: str, *, reason: str = "operator_resolved") -> bool:
        normalized_reason = str(reason or "").strip() or "operator_resolved"
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.outbox_events
                set
                    status = 'done',
                    processed_at = coalesce(processed_at, now()),
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null,
                    raw_payload = jsonb_set(
                        coalesce(raw_payload, '{}'::jsonb),
                        '{operator_resolution}',
                        jsonb_build_object('reason', %s::text, 'resolved_at', now()),
                        true
                    )
                where id = %s
                  and status = 'dead_lettered'
                returning id
                """,
                (normalized_reason, event_id),
            )
        return row is not None

    def set_statement_timeout_seconds(self, seconds: int | None) -> None:
        setter = getattr(self._connection, "set_statement_timeout_ms", None)
        if not callable(setter):
            return
        setter(None if seconds is None else max(1, int(seconds)) * 1000)

    def complete_read_model_refresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: int | str | None = None,
    ) -> bool:
        source_version_filter = ""
        params: tuple[Any, ...]
        if source_version is None:
            params = (tenant_id, scope_type, scope_key)
        else:
            source_version_filter = "and source_version <= %s"
            params = (tenant_id, scope_type, scope_key, _optional_int(source_version))
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                f"""
                update job.read_model_dirty_scopes
                set
                    status = 'done',
                    locked_by = null,
                    locked_at = null,
                    last_error = null,
                    updated_at = now()
                where tenant_id = %s
                  and scope_type = %s
                  and scope_key = %s
                  and status in ('pending', 'processing')
                  {source_version_filter}
                returning id
                """,
                params,
            )
        return row is not None

    def read_model_refresh_is_current(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: int | str | None,
    ) -> bool:
        if source_version is None:
            return True
        row = self._connection.fetch_one(
            """
            select source_version
            from job.read_model_dirty_scopes
            where tenant_id = %s
              and scope_type = %s
              and scope_key = %s
            limit 1
            """,
            (tenant_id, scope_type, scope_key),
        )
        if row is None:
            return True
        current_source_version = _optional_int(row.get("source_version"))
        event_source_version = _optional_int(source_version)
        return current_source_version is None or event_source_version is None or current_source_version <= event_source_version

    def read_model_refresh_is_active(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
    ) -> bool:
        row = self._connection.fetch_one(
            """
            select 1
            from job.outbox_events
            where tenant_id = %s
              and scope_type = %s
              and scope_key = %s
              and event_type = %s
              and status in ('pending', 'processing')
            limit 1
            """,
            (tenant_id, scope_type, scope_key, f"{scope_type}.read_model.refresh"),
        )
        return row is not None

    def read_model_refresh_is_fresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
    ) -> bool:
        row = self._connection.fetch_one(
            """
            select 1
            from job.read_model_dirty_scopes
            where tenant_id = %s
              and scope_type = %s
              and scope_key = %s
              and status in ('pending', 'processing', 'failed')
            limit 1
            """,
            (tenant_id, scope_type, scope_key),
        )
        return row is None

    def preview_runtime_queue_history_retention(
        self,
        *,
        keep_days: int = 30,
        keep_recent_per_type: int = 512,
        limit: int = 20_000,
    ) -> dict[str, Any]:
        return self._runtime_queue_history_retention(
            keep_days=keep_days,
            keep_recent_per_type=keep_recent_per_type,
            limit=limit,
            execute=False,
        )

    def prune_runtime_queue_history(
        self,
        *,
        keep_days: int = 30,
        keep_recent_per_type: int = 512,
        limit: int = 20_000,
    ) -> dict[str, Any]:
        return self._runtime_queue_history_retention(
            keep_days=keep_days,
            keep_recent_per_type=keep_recent_per_type,
            limit=limit,
            execute=True,
        )

    def _runtime_queue_history_retention(
        self,
        *,
        keep_days: int,
        keep_recent_per_type: int,
        limit: int,
        execute: bool,
    ) -> dict[str, Any]:
        normalized_keep_days = _non_negative_int(keep_days, name="keep_days")
        normalized_keep_recent_per_type = _positive_int_value(keep_recent_per_type, name="keep_recent_per_type")
        normalized_limit = _positive_int_value(limit, name="limit")
        params = (normalized_keep_days, normalized_keep_recent_per_type, normalized_limit)
        with self._connection.transaction() as transaction:
            outbox_rows = transaction.fetch_all(
                self._runtime_queue_outbox_retention_sql(execute=execute),
                params,
            )
            dirty_scope_rows = transaction.fetch_all(
                self._runtime_queue_dirty_scope_retention_sql(execute=execute),
                params,
            )
        outbox_summary = _retention_summary(outbox_rows, key_field="event_type", count_field="count")
        dirty_scope_summary = _retention_summary(dirty_scope_rows, key_field="scope_type", count_field="count")
        action_key = "deleted_count" if execute else "candidate_count"
        return {
            "mode": "execute" if execute else "dry-run",
            "policy": {
                "keep_days": normalized_keep_days,
                "keep_recent_per_type": normalized_keep_recent_per_type,
                "limit": normalized_limit,
            },
            "outbox_events": {
                action_key: outbox_summary["total_count"],
                "limit_reached": outbox_summary["total_count"] >= normalized_limit,
                "counts_by_event_type": outbox_summary["counts_by_key"],
            },
            "read_model_dirty_scopes": {
                action_key: dirty_scope_summary["total_count"],
                "limit_reached": dirty_scope_summary["total_count"] >= normalized_limit,
                "counts_by_scope_type": dirty_scope_summary["counts_by_key"],
            },
        }

    @staticmethod
    def _runtime_queue_outbox_retention_sql(*, execute: bool) -> str:
        candidate_cte = """
            with ranked as (
                select
                    event.id,
                    event.tenant_id,
                    event.event_type,
                    event.scope_type,
                    event.scope_key,
                    coalesce(event.processed_at, event.updated_at, event.created_at) as completed_at,
                    row_number() over (
                        partition by event.event_type
                        order by coalesce(event.processed_at, event.updated_at, event.created_at) desc, event.id desc
                    ) as keep_rank
                from job.outbox_events event
                where event.status = 'done'
            ),
            candidates as (
                select ranked.id, ranked.event_type, ranked.completed_at
                from ranked
                where ranked.completed_at < now() - (%s * interval '1 day')
                  and ranked.keep_rank > %s
                  and not exists (
                      select 1
                      from job.outbox_events blocker
                      where blocker.tenant_id = ranked.tenant_id
                        and blocker.event_type = ranked.event_type
                        and blocker.scope_type is not distinct from ranked.scope_type
                        and blocker.scope_key is not distinct from ranked.scope_key
                        and blocker.status in ('failed', 'dead_lettered')
                  )
                order by ranked.completed_at, ranked.id
                limit %s
            )
        """
        if execute:
            return (
                candidate_cte
                + """
                , deleted as (
                    delete from job.outbox_events event
                    using candidates
                    where event.id = candidates.id
                    returning candidates.event_type
                )
                select event_type, count(*)::bigint as count
                from deleted
                group by event_type
                order by count desc, event_type
                """
            )
        return (
            candidate_cte
            + """
            select event_type, count(*)::bigint as count
            from candidates
            group by event_type
            order by count desc, event_type
            """
        )

    @staticmethod
    def _runtime_queue_dirty_scope_retention_sql(*, execute: bool) -> str:
        candidate_cte = """
            with ranked as (
                select
                    dirty.id,
                    dirty.tenant_id,
                    dirty.scope_type,
                    dirty.scope_key,
                    coalesce(dirty.updated_at, dirty.created_at) as completed_at,
                    row_number() over (
                        partition by dirty.scope_type
                        order by coalesce(dirty.updated_at, dirty.created_at) desc, dirty.id desc
                    ) as keep_rank,
                    row_number() over (
                        partition by dirty.tenant_id, dirty.scope_type, dirty.scope_key
                        order by coalesce(dirty.updated_at, dirty.created_at) desc, dirty.id desc
                    ) as scope_keep_rank
                from job.read_model_dirty_scopes dirty
                where dirty.status = 'done'
            ),
            candidates as (
                select ranked.id, ranked.scope_type, ranked.completed_at
                from ranked
                where ranked.completed_at < now() - (%s * interval '1 day')
                  and ranked.keep_rank > %s
                  and ranked.scope_keep_rank > 1
                  and not exists (
                      select 1
                      from job.read_model_dirty_scopes blocker
                      where blocker.tenant_id = ranked.tenant_id
                        and blocker.scope_type = ranked.scope_type
                        and blocker.scope_key = ranked.scope_key
                        and blocker.status in ('pending', 'processing', 'failed')
                  )
                  and not exists (
                      select 1
                      from job.outbox_events blocker
                      where blocker.tenant_id = ranked.tenant_id
                        and blocker.event_type = ranked.scope_type || '.read_model.refresh'
                        and blocker.scope_type = ranked.scope_type
                        and blocker.scope_key = ranked.scope_key
                        and blocker.status in ('pending', 'processing', 'failed', 'dead_lettered')
                  )
                order by ranked.completed_at, ranked.id
                limit %s
            )
        """
        if execute:
            return (
                candidate_cte
                + """
                , deleted as (
                    delete from job.read_model_dirty_scopes dirty
                    using candidates
                    where dirty.id = candidates.id
                    returning candidates.scope_type
                )
                select scope_type, count(*)::bigint as count
                from deleted
                group by scope_type
                order by count desc, scope_type
                """
            )
        return (
            candidate_cte
            + """
            select scope_type, count(*)::bigint as count
            from candidates
            group by scope_type
            order by count desc, scope_type
            """
        )

    def record_worker_heartbeat(
        self,
        worker_id: str,
        worker_kind: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connection.transaction() as transaction:
            transaction.fetch_one(
                """
                insert into job.runtime_worker_heartbeats (
                    worker_id,
                    worker_kind,
                    status,
                    payload,
                    raw_payload
                )
                values (%s, %s, %s, %s, %s)
                on conflict (worker_id)
                do update set
                    worker_kind = excluded.worker_kind,
                    status = excluded.status,
                    payload = excluded.payload,
                    raw_payload = excluded.raw_payload,
                    last_seen_at = now(),
                    updated_at = now()
                returning id
                """,
                (
                    worker_id,
                    worker_kind,
                    status,
                    self._json_param(payload or {}),
                    self._json_param(payload or {}),
                ),
            )

    def backlog_summary(self) -> dict[str, object]:
        with self._connection.transaction() as transaction:
            count_rows = transaction.fetch_all(
                """
                select status, count(*)::bigint as count
                from job.outbox_events
                group by status
                order by status
                """
            )
            age_row = transaction.fetch_one(
                """
                select extract(epoch from max(now() - created_at))::float as max_pending_age_seconds
                from job.outbox_events
                where status = 'pending'
                """
            )

        return {
            "counts_by_status": {str(row["status"]): int(row["count"]) for row in count_rows},
            "max_pending_age_seconds": (age_row or {}).get("max_pending_age_seconds"),
        }

    def _json_param(self, value: dict[str, Any]) -> Any:
        if isinstance(self._connection, (PostgresConnection, PostgresTransaction)):
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        return value


def _event_from_row(row: dict[str, Any]) -> RuntimeQueueEvent:
    payload = row["payload"] if "payload" in row else {}
    if not isinstance(payload, dict):
        raise RuntimeQueueDataError(
            f"Runtime queue event {row.get('event_id')} has non-object payload of type {type(payload).__name__}."
        )
    return RuntimeQueueEvent(
        event_id=str(row["event_id"]),
        tenant_id=str(row["tenant_id"]),
        event_type=str(row["event_type"]),
        aggregate_type=_optional_str(row.get("aggregate_type")),
        aggregate_id=_optional_str(row.get("aggregate_id")),
        scope_type=_optional_str(row.get("scope_type")),
        scope_key=_optional_str(row.get("scope_key")),
        dedupe_key=_optional_str(row.get("dedupe_key")),
        payload=payload,
        attempts=int(row["attempts"]),
        status=str(row["status"]),
        schema_version=int(row.get("schema_version") or 1),
        source_version=_optional_int(row.get("source_version")),
        priority=_normalize_priority(row.get("priority") or "normal"),
        trace_id=_optional_str(row.get("trace_id")),
        publish_status=_normalize_publish_status(row.get("publish_status") or "unpublished"),
        publish_attempt_count=int(row.get("publish_attempt_count") or 0),
        rabbitmq_exchange=_optional_str(row.get("rabbitmq_exchange")),
        rabbitmq_routing_key=_optional_str(row.get("rabbitmq_routing_key")),
        rabbitmq_message_id=_optional_str(row.get("rabbitmq_message_id")),
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeQueueDataError(f"source_version must be an integer, got {value!r}.") from exc


def _safe_read_model_refresh_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}
    action_name = str(metadata.get("action_name") or "").strip()
    result: dict[str, object] = {}
    if action_name:
        result["action_name"] = action_name[:120]
    row_ids = _normalized_metadata_list(metadata.get("row_ids"))
    if row_ids:
        result["row_ids"] = row_ids
    case_ids = _normalized_metadata_list(metadata.get("case_ids"))
    if case_ids:
        result["case_ids"] = case_ids
    relation_deltas = _normalized_relation_deltas(metadata.get("relation_deltas"))
    if relation_deltas:
        result["relation_deltas"] = relation_deltas
    if metadata.get("force_refresh") is True:
        result["force_refresh"] = True
    return result


def _merge_refresh_payload_sql(existing_payload: str, incoming_payload: str) -> str:
    merged = f"({existing_payload} || {incoming_payload})"
    return f"""
                jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            {merged},
                            '{{metadata,row_ids}}',
                            {_merged_metadata_array_sql(existing_payload, incoming_payload, "row_ids")},
                            true
                        ),
                        '{{metadata,case_ids}}',
                        {_merged_metadata_array_sql(existing_payload, incoming_payload, "case_ids")},
                        true
                    ),
                    '{{metadata,relation_deltas}}',
                    {_merged_metadata_object_sql(existing_payload, incoming_payload, "relation_deltas")},
                    true
                )
            """.strip()


def _merged_metadata_array_sql(existing_payload: str, incoming_payload: str, name: str) -> str:
    path = f"'{{metadata,{name}}}'"
    return f"""
                        coalesce((
                            with merged_metadata as (
                                select value, min(ord) as first_seen
                                from (
                                    select value, ord::bigint as ord
                                    from jsonb_array_elements_text(coalesce({existing_payload} #> {path}, '[]'::jsonb))
                                        with ordinality as existing_item(value, ord)
                                    union all
                                    select value, 1000000 + ord::bigint as ord
                                    from jsonb_array_elements_text(coalesce({incoming_payload} #> {path}, '[]'::jsonb))
                                        with ordinality as incoming_item(value, ord)
                                ) metadata_items
                                where value <> ''
                                group by value
                            )
                            select case
                                when count(*) > 200 then '[]'::jsonb
                                else jsonb_agg(value order by first_seen)
                            end
                            from merged_metadata
                        ), '[]'::jsonb)
                    """.strip()


def _merged_metadata_object_sql(existing_payload: str, incoming_payload: str, name: str) -> str:
    path = f"'{{metadata,{name}}}'"
    return f"""
                        coalesce((
                            with merged_metadata(value) as (
                                values (
                                    coalesce({existing_payload} #> {path}, '{{}}'::jsonb)
                                    || coalesce({incoming_payload} #> {path}, '{{}}'::jsonb)
                                )
                            )
                            select case
                                when (select count(*) from jsonb_object_keys(value)) > 200 then '{{}}'::jsonb
                                else value
                            end
                            from merged_metadata
                        ), '{{}}'::jsonb)
                    """.strip()


def _normalized_relation_deltas(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or len(value) > 200:
        return {}
    result: dict[str, object] = {}
    for raw_case_id, raw_delta in value.items():
        case_id = str(raw_case_id or "").strip()[:240]
        if not case_id or not isinstance(raw_delta, dict):
            continue
        status = str(raw_delta.get("status") or "").strip().lower()
        row_ids = _normalized_metadata_list(raw_delta.get("row_ids"))
        if status not in {"active", "cancelled"} or not row_ids:
            continue
        result[case_id] = {"status": status, "row_ids": row_ids}
    return result


def _normalized_metadata_list(value: object) -> list[str]:
    if isinstance(value, str):
        raw_values: list[object] = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text_value = str(item or "").strip()
        if not text_value or text_value in seen:
            continue
        normalized.append(text_value[:240])
        seen.add(text_value)
    return normalized[:200]


def _normalized_scope_key_list(values: Iterable[object] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        text_value = str(value or "").strip()
        if not text_value or text_value in seen:
            continue
        normalized.append(text_value)
        seen.add(text_value)
    return sorted(normalized)


def _positive_int(raw: Any, *, default: int, name: str) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise RuntimeQueueDataError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise RuntimeQueueDataError(f"{name} must be positive.")
    return value


def _positive_int_value(raw: Any, *, name: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeQueueDataError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise RuntimeQueueDataError(f"{name} must be positive.")
    return value


def _non_negative_int(raw: Any, *, name: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeQueueDataError(f"{name} must be an integer.") from exc
    if value < 0:
        raise RuntimeQueueDataError(f"{name} must be zero or greater.")
    return value


def _retention_summary(rows: Iterable[dict[str, Any]], *, key_field: str, count_field: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    total_count = 0
    for row in list(rows or []):
        key = str(row.get(key_field) or "unknown")
        count = int(row.get(count_field) or 0)
        counts[key] = counts.get(key, 0) + count
        total_count += count
    return {"total_count": total_count, "counts_by_key": counts}


def _positive_float(raw: Any, *, default: float, name: str) -> float:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(str(raw).strip())
    except ValueError as exc:
        raise RuntimeQueueDataError(f"{name} must be a number.") from exc
    if value <= 0:
        raise RuntimeQueueDataError(f"{name} must be positive.")
    return value


def _bool(raw: Any, *, default: bool) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _event_type_tuple(raw: Any, *, default: tuple[str, ...], name: str) -> tuple[str, ...]:
    if raw is None or str(raw).strip() == "":
        return default
    values = tuple(part.strip() for part in str(raw).replace(";", ",").split(",") if part.strip())
    if not values:
        raise RuntimeQueueDataError(f"{name} must include at least one event type.")
    return values


def _normalize_priority(value: Any) -> str:
    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized not in PRIORITY_VALUES:
        raise RuntimeQueueDataError(f"priority must be one of {sorted(PRIORITY_VALUES)}.")
    return normalized


def _normalize_publish_status(value: Any) -> str:
    normalized = str(value or "unpublished").strip().lower() or "unpublished"
    if normalized not in PUBLISH_STATUS_VALUES:
        raise RuntimeQueueDataError(f"publish_status must be one of {sorted(PUBLISH_STATUS_VALUES)}.")
    return normalized
