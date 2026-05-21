from __future__ import annotations

import unittest

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
        self.heartbeats: list[tuple[str, str, str]] = []

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
        self.heartbeats.append((worker_id, worker_kind, status))


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
        self.assertIn(("worker-1", "runtime", "idle"), queue.heartbeats)

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
