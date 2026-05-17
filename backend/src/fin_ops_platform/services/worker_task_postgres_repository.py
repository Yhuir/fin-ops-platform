from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fin_ops_platform.services.worker_task_protocol import (
    WorkerDelivery,
    WorkerTaskRecord,
    WorkerTaskRepository,
    sanitize_error_detail,
)


ConnectionFactory = Callable[[], object]


class PostgresWorkerTaskRepository(WorkerTaskRepository):
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self._lease_connection: object | None = None
        self._lease_cursor: object | None = None

    @classmethod
    def from_database_url(cls, database_url: str) -> PostgresWorkerTaskRepository:
        def connect() -> object:
            try:
                import psycopg  # type: ignore[import-not-found]
                from psycopg.rows import dict_row  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError("psycopg is required for PostgreSQL worker task repository.") from exc
            return psycopg.connect(database_url, row_factory=dict_row)

        return cls(connect)

    def load_task_for_update(self, task_id: str) -> WorkerTaskRecord | None:
        self._rollback_lease()
        connection = self._connection_factory()
        cursor = connection.cursor()
        cursor.execute(
            """
            select
              id::text as id,
              task_type,
              status,
              idempotency_key,
              attempt_count,
              max_attempts
            from job.worker_tasks
            where id = %s
            for update
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            connection.rollback()
            connection.close()
            return None
        self._lease_connection = connection
        self._lease_cursor = cursor
        return _task_record(row)

    def create_attempt(
        self,
        *,
        task: WorkerTaskRecord,
        attempt_no: int,
        worker_id: str,
        delivery: WorkerDelivery,
        started_at: datetime,
    ) -> str:
        cursor = self._cursor()
        attempt_id = str(uuid4())
        cursor.execute(
            """
            insert into job.worker_attempts (
              id,
              task_id,
              attempt_no,
              worker_id,
              nats_stream,
              nats_consumer,
              nats_sequence,
              started_at,
              heartbeat_at,
              status
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'running')
            """,
            (
                attempt_id,
                task.task_id,
                attempt_no,
                worker_id,
                delivery.nats_stream,
                delivery.nats_consumer,
                delivery.nats_sequence,
                started_at,
                started_at,
            ),
        )
        return attempt_id

    def mark_task_running(self, *, task_id: str, attempt_id: str, worker_id: str, started_at: datetime) -> None:
        cursor = self._cursor()
        cursor.execute(
            """
            update job.worker_tasks
            set status = 'running',
                phase = 'running',
                attempt_count = attempt_count + 1,
                started_at = coalesce(started_at, %s),
                locked_by = %s,
                locked_at = %s,
                error_code = null,
                error_summary = null,
                updated_at = %s
            where id = %s
              and status in ('queued', 'retrying')
            """,
            (started_at, worker_id, started_at, started_at, task_id),
        )
        cursor.execute(
            """
            update app.data_reset_requests
            set status = 'running',
                execution_mode = 'maintenance_worker',
                updated_by = %s,
                updated_at = %s
            where worker_task_id = %s
              and status in ('requested', 'queued', 'running')
            """,
            (worker_id, started_at, task_id),
        )
        self._commit_lease()

    def record_heartbeat(
        self,
        *,
        task_id: str,
        attempt_id: str,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> None:
        lease_expires_at = heartbeat_at + timedelta(minutes=2)
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update job.worker_attempts
                    set heartbeat_at = %s
                    where id = %s
                      and task_id = %s
                      and worker_id = %s
                      and status = 'running'
                    """,
                    (heartbeat_at, attempt_id, task_id, worker_id),
                )
                cursor.execute(
                    """
                    insert into job.worker_heartbeats (
                      worker_id,
                      worker_kind,
                      task_id,
                      attempt_id,
                      status,
                      heartbeat_at,
                      lease_expires_at,
                      metadata,
                      updated_at
                    )
                    values (%s, 'worker_task', %s, %s, 'active', %s, %s, '{}'::jsonb, %s)
                    on conflict (worker_id) do update
                    set task_id = excluded.task_id,
                        attempt_id = excluded.attempt_id,
                        status = 'active',
                        heartbeat_at = excluded.heartbeat_at,
                        lease_expires_at = excluded.lease_expires_at,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                    """,
                    (worker_id, task_id, attempt_id, heartbeat_at, lease_expires_at, heartbeat_at),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_succeeded(
        self,
        *,
        task_id: str,
        attempt_id: str,
        result_summary: dict[str, object],
        finished_at: datetime,
    ) -> None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_finish_attempt_sql("succeeded"), (finished_at, finished_at, attempt_id, task_id))
                cursor.execute(
                    """
                    update job.worker_tasks
                    set status = 'succeeded',
                        phase = 'finished',
                        percent = 100,
                        result_summary = %s::jsonb,
                        locked_by = null,
                        locked_at = null,
                        error_code = null,
                        error_summary = null,
                        finished_at = %s,
                        updated_at = %s
                    where id = %s
                    """,
                    (_json(result_summary), finished_at, finished_at, task_id),
                )
                cursor.execute(
                    """
                    update app.data_reset_requests
                    set status = 'succeeded',
                        completed_at = %s,
                        failed_at = null,
                        failure_code = null,
                        failure_message = null,
                        updated_by = coalesce(
                          (select worker_id from job.worker_attempts where id = %s and task_id = %s),
                          updated_by
                        ),
                        updated_at = %s
                    where worker_task_id = %s
                      and status <> 'cancelled'
                    """,
                    (finished_at, attempt_id, task_id, finished_at, task_id),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_failed(
        self,
        *,
        task_id: str,
        attempt_id: str,
        error_code: str,
        error_summary: str,
        error_detail: dict[str, object],
        finished_at: datetime,
    ) -> None:
        self._finish_with_error(
            task_id=task_id,
            attempt_id=attempt_id,
            status="failed",
            phase="failed",
            error_code=error_code,
            error_summary=error_summary,
            error_detail=error_detail,
            finished_at=finished_at,
            next_attempt_at=None,
            payload=None,
        )

    def mark_retrying(
        self,
        *,
        task_id: str,
        attempt_id: str,
        error_code: str,
        error_summary: str,
        error_detail: dict[str, object],
        next_attempt_at: datetime,
        finished_at: datetime,
    ) -> None:
        self._finish_with_error(
            task_id=task_id,
            attempt_id=attempt_id,
            status="retrying",
            phase="retrying",
            error_code=error_code,
            error_summary=error_summary,
            error_detail=error_detail,
            finished_at=finished_at,
            next_attempt_at=next_attempt_at,
            payload=None,
        )

    def mark_dead_lettered(
        self,
        *,
        task_id: str,
        attempt_id: str,
        error_code: str,
        error_summary: str,
        error_detail: dict[str, object],
        payload: dict[str, object],
        finished_at: datetime,
    ) -> None:
        self._finish_with_error(
            task_id=task_id,
            attempt_id=attempt_id,
            status="dead_lettered",
            phase="dead_lettered",
            error_code=error_code,
            error_summary=error_summary,
            error_detail=error_detail,
            finished_at=finished_at,
            next_attempt_at=None,
            payload=payload,
        )

    def record_nats_dead_letter(
        self,
        *,
        envelope_payload: dict[str, object],
        error_code: str,
        error_summary: str,
        error_detail: dict[str, object],
        created_at: datetime,
    ) -> None:
        self._rollback_lease()
        source_id = _uuid_text_or_random(envelope_payload.get("message_id"))
        self._execute(
            """
            insert into job.dead_letters (
              source_kind,
              source_id,
              subject,
              task_type,
              idempotency_key,
              payload,
              error_code,
              error_summary,
              error_detail,
              created_at
            )
            values ('nats_message', %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s)
            """,
            (
                source_id,
                None,
                envelope_payload.get("task_type"),
                envelope_payload.get("idempotency_key"),
                _json(envelope_payload),
                error_code,
                error_summary,
                _json(sanitize_error_detail(error_detail)),
                created_at,
            ),
        )

    def _finish_with_error(
        self,
        *,
        task_id: str,
        attempt_id: str,
        status: str,
        phase: str,
        error_code: str,
        error_summary: str,
        error_detail: dict[str, object],
        finished_at: datetime,
        next_attempt_at: datetime | None,
        payload: dict[str, object] | None,
    ) -> None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    _finish_attempt_sql(status),
                    (
                        finished_at,
                        finished_at,
                        error_code,
                        error_summary,
                        _json(sanitize_error_detail(error_detail)),
                        attempt_id,
                        task_id,
                    ),
                )
                cursor.execute(
                    """
                    update job.worker_tasks
                    set status = %s,
                        phase = %s,
                        retryable = %s,
                        next_attempt_at = %s,
                        locked_by = null,
                        locked_at = null,
                        error_code = %s,
                        error_summary = %s,
                        finished_at = case when %s in ('failed', 'dead_lettered') then %s else finished_at end,
                        updated_at = %s
                    where id = %s
                    """,
                    (
                        status,
                        phase,
                        status == "retrying",
                        next_attempt_at,
                        error_code,
                        error_summary,
                        status,
                        finished_at,
                        finished_at,
                        task_id,
                    ),
                )
                if status in {"failed", "dead_lettered"}:
                    cursor.execute(
                        """
                        update app.data_reset_requests
                        set status = 'failed',
                            failed_at = %s,
                            failure_code = %s,
                            failure_message = %s,
                            updated_by = coalesce(
                              (select worker_id from job.worker_attempts where id = %s and task_id = %s),
                              updated_by
                            ),
                            updated_at = %s
                        where worker_task_id = %s
                          and status <> 'cancelled'
                        """,
                        (finished_at, error_code, error_summary, attempt_id, task_id, finished_at, task_id),
                    )
                if payload is not None:
                    cursor.execute(
                        """
                        insert into job.dead_letters (
                          source_kind,
                          source_id,
                          task_type,
                          idempotency_key,
                          payload,
                          error_code,
                          error_summary,
                          error_detail,
                          created_at
                        )
                        select
                          'worker_task',
                          t.id,
                          t.task_type,
                          t.idempotency_key,
                          %s::jsonb,
                          %s,
                          %s,
                          %s::jsonb,
                          %s
                        from job.worker_tasks t
                        where t.id = %s
                        """,
                        (
                            _json(payload),
                            error_code,
                            error_summary,
                            _json(sanitize_error_detail(error_detail)),
                            finished_at,
                            task_id,
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _execute(self, sql: str, params: tuple[object, ...]) -> None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _cursor(self) -> object:
        if self._lease_cursor is None:
            connection = self._connection_factory()
            self._lease_connection = connection
            self._lease_cursor = connection.cursor()
        return self._lease_cursor

    def _commit_lease(self) -> None:
        if self._lease_connection is None:
            return
        self._lease_connection.commit()
        self._lease_connection.close()
        self._lease_connection = None
        self._lease_cursor = None

    def _rollback_lease(self) -> None:
        if self._lease_connection is None:
            return
        self._lease_connection.rollback()
        self._lease_connection.close()
        self._lease_connection = None
        self._lease_cursor = None


def _finish_attempt_sql(status: str) -> str:
    if status == "succeeded":
        return """
        update job.worker_attempts
        set status = 'succeeded',
            finished_at = %s,
            duration_ms = greatest(0, floor(extract(epoch from (%s - started_at)) * 1000)::integer)
        where id = %s
          and task_id = %s
        """
    return f"""
        update job.worker_attempts
        set status = '{status}',
            finished_at = %s,
            duration_ms = greatest(0, floor(extract(epoch from (%s - started_at)) * 1000)::integer),
            error_code = %s,
            error_summary = %s,
            error_detail = %s::jsonb
        where id = %s
          and task_id = %s
        """


def _task_record(row: Mapping[str, object] | tuple[object, ...]) -> WorkerTaskRecord:
    if isinstance(row, tuple):
        task_id, task_type, status, idempotency_key, attempt_count, max_attempts = row
    else:
        task_id = row["id"]
        task_type = row["task_type"]
        status = row["status"]
        idempotency_key = row["idempotency_key"]
        attempt_count = row["attempt_count"]
        max_attempts = row["max_attempts"]
    return WorkerTaskRecord(
        task_id=str(task_id),
        task_type=str(task_type),
        status=str(status),
        idempotency_key=str(idempotency_key),
        attempt_count=int(attempt_count),
        max_attempts=int(max_attempts),
    )


def _json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _uuid_text_or_random(value: object) -> str:
    try:
        return str(UUID(str(value or "")))
    except ValueError:
        return str(uuid4())
