from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection
from fin_ops_platform.services.runtime_queue import PRIORITY_VALUES, RuntimeQueueDataError, RuntimeQueueEvent, RuntimeQueueRepository


IMPORT_PROCESS_REQUESTED_EVENT = "import.process.requested"


class ImportJobDataError(ValueError):
    pass


class ImportJobIdempotencyConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportJob:
    import_job_id: str
    tenant_id: str
    import_type: str
    import_session_id: str | None
    source_file_id: str | None
    idempotency_key: str | None
    request_fingerprint: str | None
    status: str
    stage: str
    priority: str
    attempt_count: int
    max_attempts: int
    last_error: str | None
    payload: dict[str, Any]
    result_payload: dict[str, Any]
    raw_payload: dict[str, Any]
    created_by: str | None
    trace_id: str | None


ImportJobProcessor = Callable[[ImportJob], dict[str, Any] | None]


class ImportJobRepository:
    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def create_or_get_job(
        self,
        *,
        import_type: str,
        tenant_id: str = "default",
        import_session_id: str | None = None,
        source_file_id: str | None = None,
        idempotency_key: str | None = None,
        payload: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
        created_by: str | None = None,
        trace_id: str | None = None,
        priority: str = "normal",
        max_attempts: int = 5,
        available_at: Any | None = None,
    ) -> ImportJob:
        normalized_import_type = _required_text(import_type, "import_type")
        normalized_tenant_id = _optional_text(tenant_id) or "default"
        normalized_priority = _normalize_priority(priority)
        normalized_max_attempts = _positive_int(max_attempts, "max_attempts")
        normalized_payload = _normalize_payload(payload, "payload")
        normalized_raw_payload = _normalize_payload(raw_payload, "raw_payload")
        normalized_idempotency_key = _optional_text(idempotency_key)
        request_fingerprint = _import_request_fingerprint(
            tenant_id=normalized_tenant_id,
            import_type=normalized_import_type,
            import_session_id=_optional_text(import_session_id),
            source_file_id=_optional_text(source_file_id),
            payload=normalized_payload,
        )
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                insert into job.import_jobs (
                    tenant_id,
                    import_type,
                    import_session_id,
                    source_file_id,
                    idempotency_key,
                    request_fingerprint,
                    status,
                    stage,
                    priority,
                    max_attempts,
                    payload,
                    raw_payload,
                    created_by,
                    trace_id,
                    available_at
                )
                values (%s, %s, %s, %s, %s, %s, 'pending', 'queued', %s, %s, %s, %s, %s, %s, coalesce(%s, now()))
                on conflict (tenant_id, idempotency_key)
                where idempotency_key is not null
                do update set
                    request_fingerprint = coalesce(job.import_jobs.request_fingerprint, excluded.request_fingerprint),
                    payload = case
                        when job.import_jobs.status = 'pending' then excluded.payload
                        else job.import_jobs.payload
                    end,
                    raw_payload = case
                        when job.import_jobs.status = 'pending' then excluded.raw_payload
                        else job.import_jobs.raw_payload
                    end,
                    created_by = case
                        when job.import_jobs.status = 'pending' then excluded.created_by
                        else job.import_jobs.created_by
                    end,
                    updated_at = now()
                where job.import_jobs.request_fingerprint is null
                   or job.import_jobs.request_fingerprint = excluded.request_fingerprint
                returning
                    id::text as import_job_id,
                    tenant_id,
                    import_type,
                    import_session_id,
                    source_file_id,
                    idempotency_key,
                    request_fingerprint,
                    status,
                    stage,
                    priority,
                    attempt_count,
                    max_attempts,
                    last_error,
                    payload,
                    result_payload,
                    raw_payload,
                    created_by,
                    trace_id
                """,
                (
                    normalized_tenant_id,
                    normalized_import_type,
                    _optional_text(import_session_id),
                    _optional_text(source_file_id),
                    normalized_idempotency_key,
                    request_fingerprint,
                    normalized_priority,
                    normalized_max_attempts,
                    self._json_param(normalized_payload),
                    self._json_param(normalized_raw_payload),
                    _optional_text(created_by),
                    _optional_text(trace_id),
                    available_at,
                ),
            )
        if row is None:
            raise ImportJobIdempotencyConflict("The same import idempotency key was used for a different request.")
        return _job_from_row(row)

    def get_job(self, import_job_id: str) -> ImportJob | None:
        normalized_id = _required_text(import_job_id, "import_job_id")
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                select
                    id::text as import_job_id,
                    tenant_id,
                    import_type,
                    import_session_id,
                    source_file_id,
                    idempotency_key,
                    request_fingerprint,
                    status,
                    stage,
                    priority,
                    attempt_count,
                    max_attempts,
                    last_error,
                    payload,
                    result_payload,
                    raw_payload,
                    created_by,
                    trace_id
                from job.import_jobs
                where id = %s
                """,
                (normalized_id,),
            )
        return _job_from_row(row) if row is not None else None

    def mark_processing(
        self,
        import_job_id: str,
        *,
        worker_id: str,
        stage: str = "processing",
        lock_timeout_seconds: int = 300,
    ) -> ImportJob | None:
        normalized_id = _required_text(import_job_id, "import_job_id")
        normalized_worker_id = _required_text(worker_id, "worker_id")
        normalized_stage = _optional_text(stage) or "processing"
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.import_jobs
                set
                    status = 'processing',
                    stage = %s,
                    attempt_count = attempt_count + 1,
                    started_at = coalesce(started_at, now()),
                    locked_by = %s,
                    locked_at = now(),
                    last_error = null,
                    updated_at = now()
                where id = %s
                  and (
                      (status = 'pending' and available_at <= now())
                      or (
                          status = 'processing'
                          and locked_at < now() - (%s * interval '1 second')
                      )
                  )
                returning
                    id::text as import_job_id,
                    tenant_id,
                    import_type,
                    import_session_id,
                    source_file_id,
                    idempotency_key,
                    request_fingerprint,
                    status,
                    stage,
                    priority,
                    attempt_count,
                    max_attempts,
                    last_error,
                    payload,
                    result_payload,
                    raw_payload,
                    created_by,
                    trace_id
                """,
                (normalized_stage, normalized_worker_id, normalized_id, max(1, int(lock_timeout_seconds))),
            )
        return _job_from_row(row) if row is not None else None

    def mark_retryable(
        self,
        import_job_id: str,
        *,
        worker_id: str,
        error: str,
        stage: str = "retry_pending",
    ) -> bool:
        normalized_id = _required_text(import_job_id, "import_job_id")
        normalized_worker_id = _required_text(worker_id, "worker_id")
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.import_jobs
                set
                    status = 'pending',
                    stage = %s,
                    last_error = %s,
                    available_at = now(),
                    locked_by = null,
                    locked_at = null,
                    updated_at = now()
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
                """,
                (_optional_text(stage) or "retry_pending", _required_text(error, "error"), normalized_id, normalized_worker_id),
            )
        return row is not None

    def mark_succeeded(
        self,
        import_job_id: str,
        *,
        worker_id: str,
        result_payload: dict[str, Any] | None = None,
        stage: str = "succeeded",
    ) -> bool:
        return self._finish_job(
            import_job_id,
            worker_id=worker_id,
            status="succeeded",
            stage=stage,
            result_payload=result_payload or {},
            last_error=None,
        )

    def mark_failed(
        self,
        import_job_id: str,
        *,
        worker_id: str,
        error: str,
        result_payload: dict[str, Any] | None = None,
        stage: str = "failed",
    ) -> bool:
        return self._finish_job(
            import_job_id,
            worker_id=worker_id,
            status="failed",
            stage=stage,
            result_payload=result_payload or {},
            last_error=_required_text(error, "error"),
        )

    def enqueue_process_requested(
        self,
        *,
        queue_repository: RuntimeQueueRepository,
        import_job: ImportJob,
        reason: str = "import_job_created",
    ) -> RuntimeQueueEvent:
        return queue_repository.enqueue(
            event_type=IMPORT_PROCESS_REQUESTED_EVENT,
            aggregate_type="import_job",
            aggregate_id=import_job.import_job_id,
            scope_type="import",
            scope_key=import_job.import_type,
            dedupe_key=f"{IMPORT_PROCESS_REQUESTED_EVENT}:{import_job.tenant_id}:{import_job.import_job_id}",
            payload={
                "import_job_id": import_job.import_job_id,
                "import_type": import_job.import_type,
                "reason": _optional_text(reason) or "import_job_created",
            },
            tenant_id=import_job.tenant_id,
            source_version=0,
            priority=import_job.priority,
            trace_id=import_job.trace_id,
        )

    def _finish_job(
        self,
        import_job_id: str,
        *,
        worker_id: str,
        status: str,
        stage: str,
        result_payload: dict[str, Any],
        last_error: str | None,
    ) -> bool:
        normalized_id = _required_text(import_job_id, "import_job_id")
        normalized_worker_id = _required_text(worker_id, "worker_id")
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                """
                update job.import_jobs
                set
                    status = %s,
                    stage = %s,
                    result_payload = %s,
                    last_error = %s,
                    finished_at = now(),
                    locked_by = null,
                    locked_at = null,
                    updated_at = now()
                where id = %s
                  and status = 'processing'
                  and locked_by = %s
                returning id
                """,
                (
                    status,
                    _optional_text(stage) or status,
                    self._json_param(_normalize_payload(result_payload, "result_payload")),
                    last_error,
                    normalized_id,
                    normalized_worker_id,
                ),
            )
        return row is not None

    def _json_param(self, value: dict[str, Any]) -> Any:
        if isinstance(self._connection, PostgresConnection):
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        return value


class ImportJobWorker:
    def __init__(
        self,
        *,
        repository: ImportJobRepository,
        worker_id: str,
        processors: dict[str, ImportJobProcessor] | None = None,
    ) -> None:
        self._repository = repository
        self._worker_id = _required_text(worker_id, "worker_id")
        self._processors = dict(processors or {})

    @property
    def processors(self) -> tuple[str, ...]:
        return tuple(sorted(self._processors))

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != IMPORT_PROCESS_REQUESTED_EVENT:
            raise RuntimeQueueDataError(f"Unsupported import job event type: {event.event_type}.")
        import_job_id = _required_text(event.payload.get("import_job_id"), "payload.import_job_id")
        job = self._repository.mark_processing(import_job_id, worker_id=self._worker_id)
        if job is None:
            existing = self._repository.get_job(import_job_id)
            return {
                "import_job_id": import_job_id,
                "import_job_status": existing.status if existing is not None else "missing",
                "processed": False,
            }

        processor = self._processors.get(job.import_type)
        if processor is None:
            error = f"Import processor is not registered for import_type {job.import_type!r}."
            self._repository.mark_failed(
                job.import_job_id,
                worker_id=self._worker_id,
                error=error,
                result_payload={"error_code": "processor_not_registered"},
                stage="processor_not_registered",
            )
            return {
                "import_job_id": job.import_job_id,
                "import_type": job.import_type,
                "processed": False,
                "error_code": "processor_not_registered",
            }

        try:
            processor_result = processor(job)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            if event.attempts >= job.max_attempts:
                self._repository.mark_failed(
                    job.import_job_id,
                    worker_id=self._worker_id,
                    error=error,
                    result_payload={"error_code": "processor_failed"},
                    stage="processor_failed",
                )
            else:
                self._repository.mark_retryable(
                    job.import_job_id,
                    worker_id=self._worker_id,
                    error=error,
                )
            raise

        result_payload = dict(processor_result) if isinstance(processor_result, dict) else {}
        result_payload.setdefault("import_type", job.import_type)
        if not self._repository.mark_succeeded(job.import_job_id, worker_id=self._worker_id, result_payload=result_payload):
            raise RuntimeError(f"Import job success update did not match job {job.import_job_id}.")
        return {
            "import_job_id": job.import_job_id,
            "import_type": job.import_type,
            "processed": True,
            **result_payload,
        }


def _job_from_row(row: dict[str, Any]) -> ImportJob:
    payload = _normalize_payload(row.get("payload"), "payload")
    result_payload = _normalize_payload(row.get("result_payload"), "result_payload")
    raw_payload = _normalize_payload(row.get("raw_payload"), "raw_payload")
    return ImportJob(
        import_job_id=str(row["import_job_id"]),
        tenant_id=str(row["tenant_id"]),
        import_type=str(row["import_type"]),
        import_session_id=_optional_text(row.get("import_session_id")),
        source_file_id=_optional_text(row.get("source_file_id")),
        idempotency_key=_optional_text(row.get("idempotency_key")),
        request_fingerprint=_optional_text(row.get("request_fingerprint")),
        status=str(row["status"]),
        stage=str(row["stage"]),
        priority=_normalize_priority(row.get("priority") or "normal"),
        attempt_count=int(row.get("attempt_count") or 0),
        max_attempts=int(row.get("max_attempts") or 5),
        last_error=_optional_text(row.get("last_error")),
        payload=payload,
        result_payload=result_payload,
        raw_payload=raw_payload,
        created_by=_optional_text(row.get("created_by")),
        trace_id=_optional_text(row.get("trace_id")),
    )


def _normalize_payload(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ImportJobDataError(f"{name} must be a JSON object.")
    return value


def _import_request_fingerprint(
    *,
    tenant_id: str,
    import_type: str,
    import_session_id: str | None,
    source_file_id: str | None,
    payload: dict[str, Any],
) -> str:
    business_payload = {key: value for key, value in payload.items() if key != "background_job_id"}
    encoded = json.dumps(
        {
            "tenant_id": tenant_id,
            "import_type": import_type,
            "import_session_id": import_session_id,
            "source_file_id": source_file_id,
            "payload": business_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _required_text(value: Any, name: str) -> str:
    normalized = _optional_text(value)
    if not normalized:
        raise ImportJobDataError(f"{name} is required.")
    return normalized


def _optional_text(value: Any) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _normalize_priority(value: Any) -> str:
    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized not in PRIORITY_VALUES:
        raise ImportJobDataError(f"priority must be one of {sorted(PRIORITY_VALUES)}.")
    return normalized


def _positive_int(value: Any, name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ImportJobDataError(f"{name} must be an integer.") from exc
    if normalized <= 0:
        raise ImportJobDataError(f"{name} must be positive.")
    return normalized
