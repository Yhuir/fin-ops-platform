from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable

from fin_ops_platform.services.postgres_connection import PostgresConnection
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
            )

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
    ) -> RuntimeQueueEvent:
        normalized_scope_type = str(scope_type or "").strip()
        normalized_scope_key = str(scope_key or "").strip()
        normalized_reason = str(reason or "").strip() or "read_model_refresh"
        normalized_priority = _normalize_priority(priority)
        normalized_trace_id = str(trace_id or "").strip() or None
        if not normalized_scope_type or not normalized_scope_key:
            raise RuntimeQueueDataError("scope_type and scope_key are required for read model refresh.")
        payload = {
            "scope_type": normalized_scope_type,
            "scope_key": normalized_scope_key,
            "reason": normalized_reason,
        }
        event_type = f"{normalized_scope_type}.read_model.refresh"
        dirty_row = transaction.fetch_one(
            """
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
                now(),
                %s,
                %s
            )
            on conflict (tenant_id, scope_type, scope_key)
            where status in ('pending', 'processing')
            do update set
                reason = excluded.reason,
                payload = job.read_model_dirty_scopes.payload || excluded.payload,
                raw_payload = excluded.raw_payload,
                source_version = job.read_model_dirty_scopes.source_version + 1,
                status = 'pending',
                next_run_at = now(),
                priority = excluded.priority,
                trace_id = coalesce(excluded.trace_id, job.read_model_dirty_scopes.trace_id),
                updated_at = now()
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
            """
            insert into job.outbox_events (
                tenant_id, event_type, aggregate_type, aggregate_id,
                scope_type, scope_key, dedupe_key, schema_version,
                source_version, priority, trace_id, payload, raw_payload
            )
            values (%s, %s, 'read_model', %s, %s, %s, %s, 1, %s, %s, %s, %s, %s)
            on conflict (tenant_id, dedupe_key)
            where dedupe_key is not null and status = 'pending'
            do update set
                payload = job.outbox_events.payload || excluded.payload,
                raw_payload = excluded.raw_payload,
                source_version = excluded.source_version,
                priority = excluded.priority,
                trace_id = coalesce(excluded.trace_id, job.outbox_events.trace_id),
                publish_status = 'unpublished',
                published_at = null,
                publish_last_error = null,
                next_publish_at = now(),
                publish_locked_by = null,
                publish_locked_at = null,
                publish_confirmed_at = null,
                updated_at = now()
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
    ) -> RuntimeQueueEvent | None:
        event_type_list = list(event_types or [])
        event_type_filter = ""
        params: tuple[Any, ...]
        if event_type_list:
            event_type_filter = "and event_type = any(%s)"
            params = (worker_id, lock_timeout_seconds, event_type_list)
        else:
            params = (worker_id, lock_timeout_seconds)

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
    ) -> list[RuntimeQueueEvent]:
        normalized_limit = max(1, int(limit))
        claimed: list[RuntimeQueueEvent] = []
        for _ in range(normalized_limit):
            event = self.claim_next(
                worker_id,
                event_types=event_types,
                lock_timeout_seconds=lock_timeout_seconds,
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
    ) -> RuntimeQueueEvent | None:
        event_type_list = list(event_types or [])
        event_type_filter = ""
        params: tuple[Any, ...]
        if event_type_list:
            event_type_filter = "and event_type = any(%s)"
            params = (worker_id, event_id, lock_timeout_seconds, event_type_list)
        else:
            params = (worker_id, event_id, lock_timeout_seconds)

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
        if isinstance(self._connection, PostgresConnection):
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
