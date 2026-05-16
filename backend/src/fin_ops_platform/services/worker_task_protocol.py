from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID


WORKER_TASK_SCHEMA_VERSION = "finops.worker_task.v1"
RUNNABLE_TASK_STATUSES = {"queued", "retrying"}
SENSITIVE_KEY_PARTS = ("password", "token", "secret", "credential", "uri", "url", "raw_file", "content")
SECRET_ASSIGNMENT_RE = re.compile(r"(?i)\b(password|token|secret|credential)\s*=\s*[^&\s]+")
URL_PASSWORD_RE = re.compile(r"://([^:/\s]+):([^@\s]+)@")


class WorkerProtocolError(ValueError):
    def __init__(
        self,
        error_code: str,
        error_summary: str,
        *,
        error_detail: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(error_summary)
        self.error_code = error_code
        self.error_summary = error_summary
        self.error_detail = sanitize_error_detail(dict(error_detail or {}))


class WorkerExecutionError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        error_summary: str,
        *,
        error_detail: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(error_summary)
        self.error_code = error_code
        self.error_summary = error_summary
        self.error_detail = sanitize_error_detail(dict(error_detail or {}))


class RetryableWorkerError(WorkerExecutionError):
    def __init__(
        self,
        error_code: str,
        error_summary: str,
        *,
        retry_after_seconds: int | None = None,
        error_detail: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(error_code, error_summary, error_detail=error_detail)
        self.retry_after_seconds = retry_after_seconds


class PermanentWorkerError(WorkerExecutionError):
    pass


class DeadLetterWorkerError(WorkerExecutionError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerTaskEnvelope:
    schema_version: str
    message_id: str
    task_id: str
    task_type: str
    idempotency_key: str
    trace_id: str | None
    created_at: datetime
    requested_by: str
    source: dict[str, object]
    scope: dict[str, object]
    payload: dict[str, object]
    retry: dict[str, object]
    raw_payload: dict[str, object] = field(repr=False)

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> WorkerTaskEnvelope:
        raw_payload = dict(data)
        schema_version = _required_text(raw_payload, "schema_version")
        if schema_version != WORKER_TASK_SCHEMA_VERSION:
            raise WorkerProtocolError(
                "UNSUPPORTED_WORKER_TASK_SCHEMA",
                "Unsupported worker task schema version.",
                error_detail={"schema_version": schema_version},
            )
        message_id = _required_uuid_text(raw_payload, "message_id")
        task_id = _required_uuid_text(raw_payload, "task_id")
        task_type = _required_text(raw_payload, "task_type")
        idempotency_key = _required_text(raw_payload, "idempotency_key")
        created_at = _required_datetime(raw_payload, "created_at")
        return cls(
            schema_version=schema_version,
            message_id=message_id,
            task_id=task_id,
            task_type=task_type,
            idempotency_key=idempotency_key,
            trace_id=_optional_text(raw_payload, "trace_id"),
            created_at=created_at,
            requested_by=_required_text(raw_payload, "requested_by"),
            source=_mapping(raw_payload, "source"),
            scope=_mapping(raw_payload, "scope"),
            payload=_mapping(raw_payload, "payload"),
            retry=_mapping(raw_payload, "retry"),
            raw_payload=raw_payload,
        )


@dataclass(frozen=True, slots=True)
class WorkerDelivery:
    nats_stream: str | None = None
    nats_consumer: str | None = None
    nats_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class WorkerTaskRecord:
    task_id: str
    task_type: str
    status: str
    idempotency_key: str
    attempt_count: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class WorkerAttemptLease:
    task: WorkerTaskRecord
    attempt_id: str
    attempt_no: int
    worker_id: str


@dataclass(frozen=True, slots=True)
class WorkerRunSummary:
    task_id: str
    attempt_id: str | None
    attempt_no: int | None
    status: str
    error_code: str | None = None
    error_summary: str | None = None


class WorkerTaskRepository(Protocol):
    def load_task_for_update(self, task_id: str) -> WorkerTaskRecord | None:
        ...

    def create_attempt(
        self,
        *,
        task: WorkerTaskRecord,
        attempt_no: int,
        worker_id: str,
        delivery: WorkerDelivery,
        started_at: datetime,
    ) -> str:
        ...

    def mark_task_running(self, *, task_id: str, attempt_id: str, worker_id: str, started_at: datetime) -> None:
        ...

    def record_heartbeat(
        self,
        *,
        task_id: str,
        attempt_id: str,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> None:
        ...

    def mark_succeeded(
        self,
        *,
        task_id: str,
        attempt_id: str,
        result_summary: dict[str, object],
        finished_at: datetime,
    ) -> None:
        ...

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
        ...

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
        ...

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
        ...

    def record_nats_dead_letter(
        self,
        *,
        envelope_payload: dict[str, object],
        error_code: str,
        error_summary: str,
        error_detail: dict[str, object],
        created_at: datetime,
    ) -> None:
        ...


class WorkerTaskContext:
    def __init__(
        self,
        *,
        repository: WorkerTaskRepository,
        lease: WorkerAttemptLease,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._lease = lease
        self._clock = clock

    @property
    def attempt_id(self) -> str:
        return self._lease.attempt_id

    @property
    def attempt_no(self) -> int:
        return self._lease.attempt_no

    def heartbeat(self) -> None:
        self._repository.record_heartbeat(
            task_id=self._lease.task.task_id,
            attempt_id=self._lease.attempt_id,
            worker_id=self._lease.worker_id,
            heartbeat_at=self._clock(),
        )


class WorkerTaskRunner:
    def __init__(
        self,
        *,
        repository: WorkerTaskRepository,
        worker_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        normalized_worker_id = str(worker_id or "").strip()
        if not normalized_worker_id:
            raise ValueError("worker_id is required.")
        self._repository = repository
        self._worker_id = normalized_worker_id
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(
        self,
        envelope: WorkerTaskEnvelope,
        handler: Callable[[WorkerTaskEnvelope, WorkerTaskContext], Mapping[str, object] | None],
        *,
        delivery: WorkerDelivery | None = None,
    ) -> WorkerRunSummary:
        delivery = delivery or WorkerDelivery()
        task = self._repository.load_task_for_update(envelope.task_id)
        if task is None:
            return self._dead_letter_message(
                envelope,
                error_code="WORKER_TASK_NOT_FOUND",
                error_summary="Worker task does not exist in PostgreSQL.",
            )
        protocol_error = self._validate_task_record(envelope, task)
        if protocol_error is not None:
            return self._dead_letter_message(
                envelope,
                error_code=protocol_error.error_code,
                error_summary=protocol_error.error_summary,
                error_detail=protocol_error.error_detail,
            )

        attempt_no = int(task.attempt_count) + 1
        started_at = self._clock()
        attempt_id = self._repository.create_attempt(
            task=task,
            attempt_no=attempt_no,
            worker_id=self._worker_id,
            delivery=delivery,
            started_at=started_at,
        )
        lease = WorkerAttemptLease(
            task=task,
            attempt_id=attempt_id,
            attempt_no=attempt_no,
            worker_id=self._worker_id,
        )
        self._repository.mark_task_running(
            task_id=task.task_id,
            attempt_id=attempt_id,
            worker_id=self._worker_id,
            started_at=started_at,
        )
        context = WorkerTaskContext(repository=self._repository, lease=lease, clock=self._clock)
        try:
            result_summary = handler(envelope, context)
        except DeadLetterWorkerError as exc:
            return self._mark_dead_lettered(lease, envelope, exc)
        except PermanentWorkerError as exc:
            return self._mark_failed(lease, exc)
        except RetryableWorkerError as exc:
            if attempt_no >= task.max_attempts:
                return self._mark_dead_lettered(lease, envelope, exc)
            return self._mark_retrying(lease, exc)
        except Exception as exc:
            retry_error = RetryableWorkerError(
                "UNHANDLED_WORKER_ERROR",
                str(exc) or "Unhandled worker error.",
                error_detail={"exception_type": exc.__class__.__name__},
            )
            if attempt_no >= task.max_attempts:
                return self._mark_dead_lettered(lease, envelope, retry_error)
            return self._mark_retrying(lease, retry_error)

        safe_summary = sanitize_error_detail(dict(result_summary or {}))
        self._repository.mark_succeeded(
            task_id=task.task_id,
            attempt_id=attempt_id,
            result_summary=safe_summary,
            finished_at=self._clock(),
        )
        return WorkerRunSummary(
            task_id=task.task_id,
            attempt_id=attempt_id,
            attempt_no=attempt_no,
            status="succeeded",
        )

    def _validate_task_record(
        self,
        envelope: WorkerTaskEnvelope,
        task: WorkerTaskRecord,
    ) -> WorkerProtocolError | None:
        if task.task_id != envelope.task_id:
            return WorkerProtocolError(
                "WORKER_TASK_ID_MISMATCH",
                "Loaded task id does not match worker message task_id.",
            )
        if task.task_type != envelope.task_type:
            return WorkerProtocolError(
                "WORKER_TASK_TYPE_MISMATCH",
                "Worker message task_type does not match PostgreSQL task_type.",
            )
        if task.idempotency_key != envelope.idempotency_key:
            return WorkerProtocolError(
                "WORKER_TASK_IDEMPOTENCY_MISMATCH",
                "Worker message idempotency_key does not match PostgreSQL task.",
            )
        if task.status not in RUNNABLE_TASK_STATUSES:
            return WorkerProtocolError(
                "WORKER_TASK_NOT_RUNNABLE",
                "Worker task is not queued or retrying.",
                error_detail={"status": task.status},
            )
        attempt_no = int(task.attempt_count) + 1
        if attempt_no > int(task.max_attempts):
            return WorkerProtocolError(
                "WORKER_TASK_ATTEMPTS_EXHAUSTED",
                "Worker task has no remaining attempts.",
                error_detail={"attempt_count": task.attempt_count, "max_attempts": task.max_attempts},
            )
        return None

    def _mark_failed(self, lease: WorkerAttemptLease, exc: WorkerExecutionError) -> WorkerRunSummary:
        self._repository.mark_failed(
            task_id=lease.task.task_id,
            attempt_id=lease.attempt_id,
            error_code=exc.error_code,
            error_summary=exc.error_summary,
            error_detail=exc.error_detail,
            finished_at=self._clock(),
        )
        return WorkerRunSummary(
            task_id=lease.task.task_id,
            attempt_id=lease.attempt_id,
            attempt_no=lease.attempt_no,
            status="failed",
            error_code=exc.error_code,
            error_summary=exc.error_summary,
        )

    def _mark_retrying(self, lease: WorkerAttemptLease, exc: RetryableWorkerError) -> WorkerRunSummary:
        next_attempt_at = self._clock() + timedelta(seconds=_retry_delay_seconds(lease.attempt_no, exc))
        self._repository.mark_retrying(
            task_id=lease.task.task_id,
            attempt_id=lease.attempt_id,
            error_code=exc.error_code,
            error_summary=exc.error_summary,
            error_detail=exc.error_detail,
            next_attempt_at=next_attempt_at,
            finished_at=self._clock(),
        )
        return WorkerRunSummary(
            task_id=lease.task.task_id,
            attempt_id=lease.attempt_id,
            attempt_no=lease.attempt_no,
            status="retrying",
            error_code=exc.error_code,
            error_summary=exc.error_summary,
        )

    def _mark_dead_lettered(
        self,
        lease: WorkerAttemptLease,
        envelope: WorkerTaskEnvelope,
        exc: WorkerExecutionError,
    ) -> WorkerRunSummary:
        self._repository.mark_dead_lettered(
            task_id=lease.task.task_id,
            attempt_id=lease.attempt_id,
            error_code=exc.error_code,
            error_summary=exc.error_summary,
            error_detail=exc.error_detail,
            payload=envelope.raw_payload,
            finished_at=self._clock(),
        )
        return WorkerRunSummary(
            task_id=lease.task.task_id,
            attempt_id=lease.attempt_id,
            attempt_no=lease.attempt_no,
            status="dead_lettered",
            error_code=exc.error_code,
            error_summary=exc.error_summary,
        )

    def _dead_letter_message(
        self,
        envelope: WorkerTaskEnvelope,
        *,
        error_code: str,
        error_summary: str,
        error_detail: Mapping[str, object] | None = None,
    ) -> WorkerRunSummary:
        self._repository.record_nats_dead_letter(
            envelope_payload=envelope.raw_payload,
            error_code=error_code,
            error_summary=error_summary,
            error_detail=sanitize_error_detail(dict(error_detail or {})),
            created_at=self._clock(),
        )
        return WorkerRunSummary(
            task_id=envelope.task_id,
            attempt_id=None,
            attempt_no=None,
            status="dead_lettered",
            error_code=error_code,
            error_summary=error_summary,
        )


def sanitize_error_detail(value: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, item in value.items():
        normalized_key = str(key)
        lowered_key = normalized_key.lower()
        if any(part in lowered_key for part in SENSITIVE_KEY_PARTS):
            continue
        sanitized[normalized_key] = _sanitize_value(item)
    return sanitized


def _sanitize_value(value: object) -> object:
    if isinstance(value, dict):
        return sanitize_error_detail(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_text(str(value))


def _sanitize_text(value: str) -> str:
    sanitized = URL_PASSWORD_RE.sub(r"://\1:[REDACTED]@", value)
    sanitized = SECRET_ASSIGNMENT_RE.sub("[REDACTED]", sanitized)
    lowered = sanitized.lower()
    if any(part in lowered for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    return sanitized


def _retry_delay_seconds(attempt_no: int, exc: RetryableWorkerError) -> int:
    if exc.retry_after_seconds is not None:
        return max(0, int(exc.retry_after_seconds))
    return min(3600, 30 * (2 ** max(0, min(10, attempt_no - 1))))


def _required_text(data: Mapping[str, object], field_name: str) -> str:
    value = data.get(field_name)
    text = str(value or "").strip()
    if not text:
        raise WorkerProtocolError(
            "WORKER_TASK_MESSAGE_INVALID",
            f"Worker task message field {field_name} is required.",
            error_detail={"field": field_name},
        )
    return text


def _optional_text(data: Mapping[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    text = str(value or "").strip()
    return text or None


def _required_uuid_text(data: Mapping[str, object], field_name: str) -> str:
    text = _required_text(data, field_name)
    try:
        UUID(text)
    except ValueError as exc:
        raise WorkerProtocolError(
            "WORKER_TASK_MESSAGE_INVALID",
            f"Worker task message field {field_name} must be a UUID.",
            error_detail={"field": field_name},
        ) from exc
    return text


def _required_datetime(data: Mapping[str, object], field_name: str) -> datetime:
    value = _required_text(data, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise WorkerProtocolError(
            "WORKER_TASK_MESSAGE_INVALID",
            f"Worker task message field {field_name} must be ISO-8601 datetime.",
            error_detail={"field": field_name},
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _mapping(data: Mapping[str, object], field_name: str) -> dict[str, object]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise WorkerProtocolError(
            "WORKER_TASK_MESSAGE_INVALID",
            f"Worker task message field {field_name} must be an object.",
            error_detail={"field": field_name},
        )
    return dict(value)
