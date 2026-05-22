from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fin_ops_platform.services.postgres_connection import PostgresConnection


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


class RuntimeQueueDataError(ValueError):
    pass


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
    ) -> RuntimeQueueEvent:
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
                    available_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()))
                on conflict (tenant_id, dedupe_key)
                where dedupe_key is not null and status in ('pending', 'processing')
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
                    status
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
    ) -> RuntimeQueueEvent:
        normalized_scope_type = str(scope_type or "").strip()
        normalized_scope_key = str(scope_key or "").strip()
        normalized_reason = str(reason or "").strip() or "read_model_refresh"
        if not normalized_scope_type or not normalized_scope_key:
            raise RuntimeQueueDataError("scope_type and scope_key are required for read model refresh.")
        payload = {
            "scope_type": normalized_scope_type,
            "scope_key": normalized_scope_key,
            "reason": normalized_reason,
        }
        event_type = f"{normalized_scope_type}.read_model.refresh"
        with self._connection.transaction() as transaction:
            dirty_row = transaction.fetch_one(
                """
                insert into job.read_model_dirty_scopes(
                    tenant_id, scope_type, scope_key, reason, payload, raw_payload, status, next_run_at
                )
                values (%s, %s, %s, %s, %s, %s, 'pending', now())
                on conflict (tenant_id, scope_type, scope_key)
                where status in ('pending', 'processing')
                do update set
                    reason = excluded.reason,
                    payload = job.read_model_dirty_scopes.payload || excluded.payload,
                    raw_payload = excluded.raw_payload,
                    source_version = job.read_model_dirty_scopes.source_version + 1,
                    status = 'pending',
                    next_run_at = now(),
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
                ),
            )
            source_version = int((dirty_row or {}).get("source_version") or 0)
            payload = {**payload, "source_version": source_version}
            row = transaction.fetch_one(
                """
                insert into job.outbox_events (
                    tenant_id, event_type, aggregate_type, aggregate_id,
                    scope_type, scope_key, dedupe_key, payload
                )
                values (%s, %s, 'read_model', %s, %s, %s, %s, %s)
                on conflict (tenant_id, dedupe_key)
                where dedupe_key is not null and status in ('pending', 'processing')
                do update set
                    payload = job.outbox_events.payload || excluded.payload,
                    raw_payload = excluded.raw_payload,
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
                    status
                """,
                (
                    tenant_id,
                    event_type,
                    normalized_scope_key,
                    normalized_scope_type,
                    normalized_scope_key,
                    f"{event_type}:{normalized_scope_type}:{normalized_scope_key}",
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
                    order by available_at, created_at, id
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
                    job.outbox_events.status
                """,
                params,
            )
            return _event_from_row(row) if row is not None else None

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
                    updated_at = now(),
                    locked_by = null,
                    locked_at = null
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
            """
            params = (error, retry_delay_seconds, event_id, worker_id)
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

    def set_statement_timeout_seconds(self, seconds: int | None) -> None:
        setter = getattr(self._connection, "set_statement_timeout_ms", None)
        if not callable(setter):
            return
        setter(None if seconds is None else max(1, int(seconds)) * 1000)

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> bool:
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
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
                returning id
                """,
                (tenant_id, scope_type, scope_key),
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
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None
