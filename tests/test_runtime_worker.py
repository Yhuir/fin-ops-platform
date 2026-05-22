from __future__ import annotations

import unittest
from time import sleep

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.runtime_worker import RuntimeWorker, RuntimeWorkerConfig, RuntimeWorkerResult


def event(event_type: str = "runtime.test") -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id="event-1",
        tenant_id="default",
        event_type=event_type,
        aggregate_type=None,
        aggregate_id=None,
        scope_type=None,
        scope_key=None,
        dedupe_key=None,
        payload={"ok": True},
        attempts=0,
        status="pending",
    )


class FakeQueue:
    def __init__(self, claimed: RuntimeQueueEvent | None) -> None:
        self.claimed = claimed
        self.claim_calls: list[tuple[str, list[str] | None, int]] = []
        self.completed: list[tuple[str, str, dict[str, object] | None]] = []
        self.failed: list[tuple[str, str, str, bool, int]] = []
        self.heartbeats: list[tuple[str, str, str, object]] = []
        self.statement_timeouts: list[int | None] = []

    def claim_next(self, worker_id: str, event_types=None, lock_timeout_seconds: int = 300):
        self.claim_calls.append((worker_id, list(event_types) if event_types is not None else None, lock_timeout_seconds))
        return self.claimed

    def complete(self, event_id: str, worker_id: str, result_payload=None) -> bool:
        self.completed.append((event_id, worker_id, result_payload))
        return True

    def fail(self, event_id: str, worker_id: str, error: str, retry: bool = True, retry_delay_seconds: int = 60) -> bool:
        self.failed.append((event_id, worker_id, error, retry, retry_delay_seconds))
        return True

    def record_worker_heartbeat(self, worker_id: str, worker_kind: str, status: str, payload=None) -> None:
        self.heartbeats.append((worker_id, worker_kind, status, payload))

    def set_statement_timeout_seconds(self, seconds: int | None) -> None:
        self.statement_timeouts.append(seconds)


class RuntimeWorkerTests(unittest.TestCase):
    def test_run_once_claims_from_postgres_queue_without_redis_and_completes_event(self) -> None:
        queue = FakeQueue(event())
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["runtime.test"], lock_timeout_seconds=120),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.PROCESSED)
        self.assertEqual(queue.claim_calls, [("worker-1", ["runtime.test"], 120)])
        self.assertEqual(queue.completed, [("event-1", "worker-1", {"handled": "event-1"})])
        self.assertEqual(queue.failed, [])
        self.assertTrue(any(status == "idle" for _worker_id, _kind, status, _payload in queue.heartbeats))

    def test_run_once_retries_handler_exception_with_configured_delay(self) -> None:
        queue = FakeQueue(event())

        def fail(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("transient failure")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["runtime.test"], retry_delay_seconds=75),
            handlers={"runtime.test": fail},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.FAILED_RETRYABLE)
        self.assertEqual(queue.completed, [])
        self.assertEqual(queue.failed, [("event-1", "worker-1", "transient failure", True, 75)])

    def test_run_once_sets_statement_timeout_and_processing_heartbeat_for_claimed_event(self) -> None:
        queue = FakeQueue(event())
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                statement_timeout_seconds=12,
            ),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.PROCESSED)
        self.assertEqual(queue.statement_timeouts, [12, None])
        processing = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "processing"]
        self.assertEqual(processing[0]["event_id"], "event-1")
        self.assertEqual(processing[0]["event_type"], "runtime.test")

    def test_run_once_retries_when_handler_exceeds_task_timeout(self) -> None:
        queue = FakeQueue(event())

        def slow_handler(_event: RuntimeQueueEvent) -> None:
            sleep(2)

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                task_timeout_seconds=1,
                retry_delay_seconds=7,
            ),
            handlers={"runtime.test": slow_handler},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.FAILED_RETRYABLE)
        self.assertEqual(queue.completed, [])
        self.assertEqual(len(queue.failed), 1)
        self.assertEqual(queue.failed[0][0], "event-1")
        self.assertIn("runtime worker task exceeded 1s timeout", queue.failed[0][2])
        self.assertEqual(queue.failed[0][3:], (True, 7))

    def test_run_once_does_not_claim_when_no_event_types_or_handlers_are_registered(self) -> None:
        queue = FakeQueue(event())
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1"),
            handlers={},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.IDLE)
        self.assertEqual(queue.claim_calls, [])
        self.assertEqual(queue.completed, [])
        self.assertEqual(queue.failed, [])


if __name__ == "__main__":
    unittest.main()
