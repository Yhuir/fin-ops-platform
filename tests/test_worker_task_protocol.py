from __future__ import annotations

import unittest
from datetime import UTC, datetime

from fin_ops_platform.services.worker_task_protocol import (
    DeadLetterWorkerError,
    PermanentWorkerError,
    RetryableWorkerError,
    WorkerDelivery,
    WorkerProtocolError,
    WorkerTaskEnvelope,
    WorkerTaskRecord,
    WorkerTaskRunner,
    sanitize_error_detail,
)


FIXED_NOW = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)


def valid_message(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "finops.worker_task.v1",
        "message_id": "11111111-1111-4111-8111-111111111111",
        "task_id": "22222222-2222-4222-8222-222222222222",
        "task_type": "read_model.rebuild",
        "idempotency_key": "read_model.rebuild:workbench:2026-05:v42",
        "trace_id": "trace-001",
        "created_at": "2026-05-16T10:00:00Z",
        "requested_by": "system",
        "source": {
            "aggregate_type": "import_batch",
            "aggregate_id": "33333333-3333-4333-8333-333333333333",
            "event_id": "44444444-4444-4444-8444-444444444444",
        },
        "scope": {"months": ["2026-05"], "scope_keys": ["workbench:2026-05"]},
        "payload": {"model": "workbench"},
        "retry": {"attempt": 1, "max_attempts": 3},
    }
    payload.update(overrides)
    return payload


class FakeWorkerRepository:
    def __init__(self, task: WorkerTaskRecord | None) -> None:
        self.task = task
        self.events: list[str] = []
        self.attempts: list[dict[str, object]] = []
        self.dead_letters: list[dict[str, object]] = []
        self.task_status: str | None = task.status if task is not None else None
        self.attempt_status: str | None = None
        self.next_attempt_at: datetime | None = None

    def load_task_for_update(self, task_id: str) -> WorkerTaskRecord | None:
        self.events.append(f"load:{task_id}")
        return self.task

    def create_attempt(
        self,
        *,
        task: WorkerTaskRecord,
        attempt_no: int,
        worker_id: str,
        delivery: WorkerDelivery,
        started_at: datetime,
    ) -> str:
        self.events.append("create_attempt")
        attempt_id = f"attempt-{attempt_no}"
        self.attempts.append(
            {
                "attempt_id": attempt_id,
                "task_id": task.task_id,
                "attempt_no": attempt_no,
                "worker_id": worker_id,
                "nats_stream": delivery.nats_stream,
                "nats_consumer": delivery.nats_consumer,
                "nats_sequence": delivery.nats_sequence,
                "started_at": started_at,
            }
        )
        self.attempt_status = "running"
        return attempt_id

    def mark_task_running(self, *, task_id: str, attempt_id: str, worker_id: str, started_at: datetime) -> None:
        self.events.append("mark_running")
        self.task_status = "running"

    def record_heartbeat(
        self,
        *,
        task_id: str,
        attempt_id: str,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> None:
        self.events.append("heartbeat")

    def mark_succeeded(
        self,
        *,
        task_id: str,
        attempt_id: str,
        result_summary: dict[str, object],
        finished_at: datetime,
    ) -> None:
        self.events.append("mark_succeeded")
        self.task_status = "succeeded"
        self.attempt_status = "succeeded"

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
        self.events.append(f"mark_failed:{error_code}")
        self.task_status = "failed"
        self.attempt_status = "failed"

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
        self.events.append(f"mark_retrying:{error_code}")
        self.task_status = "retrying"
        self.attempt_status = "retrying"
        self.next_attempt_at = next_attempt_at

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
        self.events.append(f"mark_dead_lettered:{error_code}")
        self.task_status = "dead_lettered"
        self.attempt_status = "dead_lettered"
        self.dead_letters.append(
            {
                "source_kind": "worker_task",
                "source_id": task_id,
                "error_code": error_code,
                "error_summary": error_summary,
                "payload": payload,
            }
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
        self.events.append(f"record_nats_dead_letter:{error_code}")
        self.dead_letters.append(
            {
                "source_kind": "nats_message",
                "source_id": str(envelope_payload.get("message_id") or ""),
                "error_code": error_code,
                "error_summary": error_summary,
                "payload": envelope_payload,
            }
        )


class WorkerTaskProtocolTests(unittest.TestCase):
    def _task(self, *, attempt_count: int = 0, max_attempts: int = 3) -> WorkerTaskRecord:
        return WorkerTaskRecord(
            task_id="22222222-2222-4222-8222-222222222222",
            task_type="read_model.rebuild",
            status="queued",
            idempotency_key="read_model.rebuild:workbench:2026-05:v42",
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        )

    def _runner(self, repository: FakeWorkerRepository) -> WorkerTaskRunner:
        return WorkerTaskRunner(
            repository=repository,
            worker_id="worker-1",
            clock=lambda: FIXED_NOW,
        )

    def test_envelope_rejects_unsupported_schema_version(self) -> None:
        with self.assertRaises(WorkerProtocolError) as raised:
            WorkerTaskEnvelope.from_mapping(valid_message(schema_version="finops.worker_task.v0"))

        self.assertEqual(raised.exception.error_code, "UNSUPPORTED_WORKER_TASK_SCHEMA")

    def test_success_writes_attempt_before_handler_and_records_heartbeat(self) -> None:
        repository = FakeWorkerRepository(self._task())
        envelope = WorkerTaskEnvelope.from_mapping(valid_message())
        delivery = WorkerDelivery(nats_stream="FINOPS_JOBS", nats_consumer="read-model-workers", nats_sequence=42)

        def handler(message: WorkerTaskEnvelope, context) -> dict[str, object]:
            self.assertEqual(message.task_type, "read_model.rebuild")
            repository.events.append("handler_called")
            context.heartbeat()
            return {"rebuilt": 7}

        result = self._runner(repository).run(envelope, handler, delivery=delivery)

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(repository.events[:4], ["load:22222222-2222-4222-8222-222222222222", "create_attempt", "mark_running", "handler_called"])
        self.assertIn("heartbeat", repository.events)
        self.assertEqual(repository.task_status, "succeeded")
        self.assertEqual(repository.attempt_status, "succeeded")
        self.assertEqual(repository.attempts[0]["attempt_no"], 1)
        self.assertEqual(repository.attempts[0]["nats_sequence"], 42)

    def test_retryable_error_marks_retrying_before_max_attempts(self) -> None:
        repository = FakeWorkerRepository(self._task(attempt_count=1, max_attempts=3))
        envelope = WorkerTaskEnvelope.from_mapping(valid_message(retry={"attempt": 2, "max_attempts": 3}))

        def handler(_message: WorkerTaskEnvelope, _context) -> dict[str, object]:
            raise RetryableWorkerError("OBJECT_STORE_TIMEOUT", "object storage timed out", retry_after_seconds=30)

        result = self._runner(repository).run(envelope, handler)

        self.assertEqual(result.status, "retrying")
        self.assertEqual(repository.task_status, "retrying")
        self.assertEqual(repository.attempt_status, "retrying")
        self.assertEqual(repository.next_attempt_at, datetime(2026, 5, 16, 10, 0, 30, tzinfo=UTC))
        self.assertIn("mark_retrying:OBJECT_STORE_TIMEOUT", repository.events)

    def test_retry_exhaustion_marks_task_dead_lettered_and_keeps_payload(self) -> None:
        repository = FakeWorkerRepository(self._task(attempt_count=2, max_attempts=3))
        envelope = WorkerTaskEnvelope.from_mapping(valid_message(retry={"attempt": 3, "max_attempts": 3}))

        def handler(_message: WorkerTaskEnvelope, _context) -> dict[str, object]:
            raise RetryableWorkerError("OA_SOURCE_UNAVAILABLE", "OA source unavailable")

        result = self._runner(repository).run(envelope, handler)

        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(repository.task_status, "dead_lettered")
        self.assertEqual(repository.dead_letters[0]["source_kind"], "worker_task")
        self.assertEqual(repository.dead_letters[0]["error_code"], "OA_SOURCE_UNAVAILABLE")
        self.assertEqual(repository.dead_letters[0]["payload"]["task_id"], envelope.task_id)

    def test_permanent_error_marks_task_failed_without_dead_letter(self) -> None:
        repository = FakeWorkerRepository(self._task())
        envelope = WorkerTaskEnvelope.from_mapping(valid_message())

        def handler(_message: WorkerTaskEnvelope, _context) -> dict[str, object]:
            raise PermanentWorkerError("INVALID_IMPORT_TEMPLATE", "template is not supported")

        result = self._runner(repository).run(envelope, handler)

        self.assertEqual(result.status, "failed")
        self.assertEqual(repository.task_status, "failed")
        self.assertEqual(repository.dead_letters, [])
        self.assertIn("mark_failed:INVALID_IMPORT_TEMPLATE", repository.events)

    def test_explicit_dead_letter_error_marks_task_dead_lettered(self) -> None:
        repository = FakeWorkerRepository(self._task())
        envelope = WorkerTaskEnvelope.from_mapping(valid_message())

        def handler(_message: WorkerTaskEnvelope, _context) -> dict[str, object]:
            raise DeadLetterWorkerError("SCHEMA_INCOMPATIBLE", "payload cannot be decoded")

        result = self._runner(repository).run(envelope, handler)

        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(repository.task_status, "dead_lettered")
        self.assertEqual(repository.dead_letters[0]["error_code"], "SCHEMA_INCOMPATIBLE")

    def test_missing_task_records_nats_dead_letter_and_does_not_run_handler(self) -> None:
        repository = FakeWorkerRepository(None)
        envelope = WorkerTaskEnvelope.from_mapping(valid_message())
        handler_called = False

        def handler(_message: WorkerTaskEnvelope, _context) -> dict[str, object]:
            nonlocal handler_called
            handler_called = True
            return {}

        result = self._runner(repository).run(envelope, handler)

        self.assertFalse(handler_called)
        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(repository.attempts, [])
        self.assertEqual(repository.dead_letters[0]["source_kind"], "nats_message")
        self.assertEqual(repository.dead_letters[0]["error_code"], "WORKER_TASK_NOT_FOUND")

    def test_error_detail_sanitizes_secret_keys_and_secret_values(self) -> None:
        sanitized = sanitize_error_detail(
            {
                "database_url": "postgres://user:password@example.test/db?token=abc",
                "nested": {"api_secret": "secret-value", "message": "failed with token=abc"},
                "safe": "kept",
            }
        )

        serialized = str(sanitized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("token=abc", serialized)
        self.assertNotIn("secret-value", serialized)
        self.assertEqual(sanitized["safe"], "kept")


if __name__ == "__main__":
    unittest.main()
