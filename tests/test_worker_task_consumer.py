from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime

from fin_ops_platform.services.worker_task_consumer import consume_worker_message
from fin_ops_platform.services.worker_task_protocol import WorkerTaskRecord

from tests.test_worker_task_protocol import FakeWorkerRepository, valid_message


FIXED_NOW = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)


class FakeNatsMessage:
    def __init__(self, payload: dict[str, object] | bytes) -> None:
        self.data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.acked = False
        self.naked = False
        self.terminated = False
        self.nak_delay: float | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nak(self, delay: float | None = None) -> None:
        self.naked = True
        self.nak_delay = delay

    async def term(self) -> None:
        self.terminated = True


class WorkerTaskConsumerTests(unittest.TestCase):
    def _task(self, *, attempt_count: int = 0, max_attempts: int = 3) -> WorkerTaskRecord:
        return WorkerTaskRecord(
            task_id="22222222-2222-4222-8222-222222222222",
            task_type="read_model.rebuild",
            status="queued",
            idempotency_key="read_model.rebuild:workbench:2026-05:v42",
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        )

    def test_successful_message_is_acked_after_runner_finishes(self) -> None:
        repository = FakeWorkerRepository(self._task())
        message = FakeNatsMessage(valid_message())

        async def run() -> None:
            result = await consume_worker_message(
                message,
                repository=repository,
                worker_id="worker-1",
                handler=lambda _envelope, _context: {"rebuilt": 3},
                clock=lambda: FIXED_NOW,
            )
            self.assertEqual(result.status, "succeeded")

        asyncio.run(run())

        self.assertTrue(message.acked)
        self.assertFalse(message.naked)
        self.assertEqual(repository.task_status, "succeeded")

    def test_retrying_message_is_naked_without_ack(self) -> None:
        repository = FakeWorkerRepository(self._task())
        message = FakeNatsMessage(valid_message())

        async def run() -> None:
            from fin_ops_platform.services.worker_task_protocol import RetryableWorkerError

            result = await consume_worker_message(
                message,
                repository=repository,
                worker_id="worker-1",
                handler=lambda _envelope, _context: (_ for _ in ()).throw(
                    RetryableWorkerError("OBJECT_STORE_TIMEOUT", "object storage timed out", retry_after_seconds=45)
                ),
                clock=lambda: FIXED_NOW,
            )
            self.assertEqual(result.status, "retrying")

        asyncio.run(run())

        self.assertFalse(message.acked)
        self.assertTrue(message.naked)
        self.assertEqual(message.nak_delay, 45)

    def test_invalid_json_is_recorded_as_nats_dead_letter_and_terminated(self) -> None:
        repository = FakeWorkerRepository(None)
        message = FakeNatsMessage(b"{not-json")

        async def run() -> None:
            result = await consume_worker_message(
                message,
                repository=repository,
                worker_id="worker-1",
                handler=lambda _envelope, _context: {},
                clock=lambda: FIXED_NOW,
            )
            self.assertEqual(result.status, "dead_lettered")

        asyncio.run(run())

        self.assertFalse(message.acked)
        self.assertTrue(message.terminated)
        self.assertEqual(repository.dead_letters[0]["source_kind"], "nats_message")
        self.assertEqual(repository.dead_letters[0]["error_code"], "WORKER_TASK_MESSAGE_INVALID")


if __name__ == "__main__":
    unittest.main()
