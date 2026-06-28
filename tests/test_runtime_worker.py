from __future__ import annotations

import unittest
from time import sleep

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.runtime_worker import (
    RuntimeWorker,
    RuntimeWorkerConfig,
    RuntimeWorkerResult,
    RuntimeWorkerShutdownRequested,
)


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
        self.acked: list[tuple[str, str, dict[str, object] | None]] = []
        self.failed: list[tuple[str, str, str, bool, int]] = []
        self.failed_events: list[tuple[str, str, str, bool, int, int]] = []
        self.released_events: list[tuple[str, str, str]] = []
        self.deferred_events: list[tuple[str, str, str, int]] = []
        self.heartbeats: list[tuple[str, str, str, object]] = []
        self.statement_timeouts: list[int | None] = []

    def claim_next(self, worker_id: str, event_types=None, lock_timeout_seconds: int = 300):
        self.claim_calls.append((worker_id, list(event_types) if event_types is not None else None, lock_timeout_seconds))
        return self.claimed

    def complete(self, event_id: str, worker_id: str, result_payload=None) -> bool:
        self.completed.append((event_id, worker_id, result_payload))
        return True

    def ack_event(self, event_id: str, worker_id: str, result_payload=None) -> bool:
        self.acked.append((event_id, worker_id, result_payload))
        return True

    def fail(self, event_id: str, worker_id: str, error: str, retry: bool = True, retry_delay_seconds: int = 60) -> bool:
        self.failed.append((event_id, worker_id, error, retry, retry_delay_seconds))
        return True

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
        self.failed_events.append((event_id, worker_id, error, retryable, retry_delay_seconds, max_attempts))
        return True

    def release_event(self, event_id: str, worker_id: str, *, reason: str = "worker_shutdown") -> bool:
        self.released_events.append((event_id, worker_id, reason))
        return True

    def defer_event(
        self,
        event_id: str,
        worker_id: str,
        *,
        reason: str = "dependency_not_ready",
        delay_seconds: int = 2,
    ) -> bool:
        self.deferred_events.append((event_id, worker_id, reason, delay_seconds))
        return True

    def record_worker_heartbeat(self, worker_id: str, worker_kind: str, status: str, payload=None) -> None:
        self.heartbeats.append((worker_id, worker_kind, status, payload))

    def set_statement_timeout_seconds(self, seconds: int | None) -> None:
        self.statement_timeouts.append(seconds)


class FakeSequenceQueue(FakeQueue):
    def __init__(self, claimed_events: list[RuntimeQueueEvent]) -> None:
        super().__init__(None)
        self.claimed_events = list(claimed_events)

    def claim_next(self, worker_id: str, event_types=None, lock_timeout_seconds: int = 300):
        self.claim_calls.append((worker_id, list(event_types) if event_types is not None else None, lock_timeout_seconds))
        return self.claimed_events.pop(0) if self.claimed_events else None


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
        self.assertEqual(queue.acked[0][0:2], ("event-1", "worker-1"))
        self.assertEqual(queue.acked[0][2]["handled"], "event-1")
        self.assertIn("duration_ms", queue.acked[0][2])
        self.assertEqual(queue.completed, [])
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
        self.assertEqual(queue.failed_events, [("event-1", "worker-1", "transient failure", True, 75, 5)])

    def test_run_once_defers_dependency_not_fresh_without_marking_failed(self) -> None:
        queue = FakeQueue(event())

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("legacy_sample_read_model_not_fresh: status=refreshing")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                dependency_not_fresh_delay_seconds=0.25,
            ),
            handlers={"runtime.test": fail_not_fresh},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.failed_events, [])
        self.assertEqual(queue.deferred_events, [("event-1", "worker-1", "legacy_sample_read_model_not_fresh: status=refreshing", 0.25)])
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertNotIn("dependency_refreshes", deferred_payloads[0])

    def test_run_once_defers_dependency_not_fresh_without_enqueueing_dependency_refresh(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("background.sample.changed").__dict__,
                "scope_type": "legacy_sample",
                "scope_key": "2026-04",
                "priority": "normal",
                "trace_id": "trace-dep-1",
            }
        )
        queue = FakeQueue(claimed)

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("bank_detail_read_model_not_fresh")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["background.sample.changed"],
                dependency_not_fresh_delay_seconds=4,
            ),
            handlers={"background.sample.changed": fail_not_fresh},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.deferred_events, [("event-1", "worker-1", "bank_detail_read_model_not_fresh", 4)])
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertNotIn("dependency_refreshes", deferred_payloads[0])

    def test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("background.sample.changed").__dict__,
                "scope_type": "legacy_sample",
                "scope_key": "all",
                "priority": "high",
            }
        )
        queue = FakeQueue(claimed)

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("bank_detail_read_model_not_fresh")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["background.sample.changed"]),
            handlers={"background.sample.changed": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertNotIn("dependency_refreshes", deferred_payloads[0])

    def test_run_once_does_not_probe_dependency_refresh_active_state(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("background.sample.changed").__dict__,
                "tenant_id": "tenant-a",
                "scope_type": "legacy_sample",
                "scope_key": "2026-04",
                "priority": "normal",
            }
        )
        queue = FakeQueue(claimed)

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("bank_detail_read_model_not_fresh")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["background.sample.changed"]),
            handlers={"background.sample.changed": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertNotIn("dependency_refreshes", deferred_payloads[0])

    def test_run_once_does_not_probe_dependency_refresh_fresh_state(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("background.sample.changed").__dict__,
                "tenant_id": "tenant-a",
                "scope_type": "legacy_sample",
                "scope_key": "2026-03",
                "priority": "high",
            }
        )
        queue = FakeQueue(claimed)

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("bank_detail_read_model_not_fresh")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["background.sample.changed"]),
            handlers={"background.sample.changed": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertNotIn("dependency_refreshes", deferred_payloads[0])

    def test_run_once_defers_same_scope_parent_inconsistent_without_dependency_refresh(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("background.sample.changed").__dict__,
                "tenant_id": "tenant-a",
                "scope_type": "legacy_sample",
                "scope_key": "all",
                "priority": "normal",
                "trace_id": "trace-workbench-all",
            }
        )
        queue = FakeQueue(claimed)

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError(
                "legacy_sample_read_model_not_fresh: parent_generation_inconsistent "
                "parent_scope_keys=2026-03"
            )

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["background.sample.changed"],
                dependency_not_fresh_delay_seconds=4,
                retry_delay_seconds=60,
            ),
            handlers={"background.sample.changed": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.failed_events, [])
        self.assertEqual(
            queue.deferred_events,
            [
                (
                    "event-1",
                    "worker-1",
                    "legacy_sample_read_model_not_fresh: parent_generation_inconsistent parent_scope_keys=2026-03",
                    4,
                )
            ],
        )
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertEqual(deferred_payloads[0]["delay_seconds"], 4)
        self.assertNotIn("dependency_refreshes", deferred_payloads[0])

    def test_run_once_uses_exponential_retry_delay_and_max_attempts(self) -> None:
        claimed = event()
        claimed = RuntimeQueueEvent(**{**claimed.__dict__, "attempts": 3})
        queue = FakeQueue(claimed)

        def fail(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("transient failure")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                retry_delay_seconds=10,
                max_attempts=4,
            ),
            handlers={"runtime.test": fail},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.FAILED_RETRYABLE)
        self.assertEqual(queue.failed_events, [("event-1", "worker-1", "transient failure", True, 40, 4)])

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

    def test_heartbeats_include_worker_instance_when_configured(self) -> None:
        queue = FakeQueue(None)
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="host-workbench",
                worker_kind="workbench-read-model",
                worker_instance="legacy_sample",
                event_types=["runtime.test"],
            ),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.IDLE)
        self.assertTrue(queue.heartbeats)
        for _worker_id, _kind, _status, payload in queue.heartbeats:
            self.assertEqual(payload["worker_instance"], "legacy_sample")

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
        self.assertEqual(len(queue.failed_events), 1)
        self.assertEqual(queue.failed_events[0][0], "event-1")
        self.assertIn("runtime worker task exceeded 1s timeout", queue.failed_events[0][2])
        self.assertEqual(queue.failed_events[0][3:], (True, 7, 5))

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

    def test_run_forever_drains_multiple_events_before_idle_sleep(self) -> None:
        events = [
            RuntimeQueueEvent(**{**event().__dict__, "event_id": f"event-{index}"})
            for index in range(1, 5)
        ]
        queue = FakeSequenceQueue(events)
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                max_iterations=1,
                max_events_per_iteration=3,
            ),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        worker.run_forever()

        self.assertEqual([event_id for event_id, _worker_id, _payload in queue.acked], ["event-1", "event-2", "event-3"])
        self.assertEqual(len(queue.claim_calls), 3)
        self.assertEqual([claimed.event_id for claimed in queue.claimed_events], ["event-4"])

    def test_run_forever_releases_claimed_event_on_shutdown_request(self) -> None:
        queue = FakeQueue(event())

        def stop(_event: RuntimeQueueEvent) -> None:
            raise RuntimeWorkerShutdownRequested(15)

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["runtime.test"]),
            handlers={"runtime.test": stop},
        )

        worker.run_forever()

        self.assertEqual(queue.released_events, [("event-1", "worker-1", "shutdown_signal_15")])
        self.assertEqual(queue.acked, [])
        self.assertEqual(queue.failed_events, [])
        statuses = [status for _worker_id, _kind, status, _payload in queue.heartbeats]
        self.assertIn("stopping", statuses)
        self.assertIn("stopped", statuses)


if __name__ == "__main__":
    unittest.main()
