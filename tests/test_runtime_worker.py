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
        self.enqueued_read_model_refreshes: list[dict[str, object]] = []
        self.active_read_model_refreshes: set[tuple[str, str, str]] = set()
        self.active_read_model_refresh_checks: list[tuple[str, str, str]] = []
        self.fresh_read_model_refreshes: set[tuple[str, str, str]] = set()
        self.fresh_read_model_refresh_checks: list[tuple[str, str, str]] = []
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

    def enqueue_read_model_refresh(self, **kwargs: object) -> RuntimeQueueEvent:
        self.enqueued_read_model_refreshes.append(dict(kwargs))
        return RuntimeQueueEvent(
            event_id=f"dep-{len(self.enqueued_read_model_refreshes)}",
            tenant_id=str(kwargs.get("tenant_id") or "default"),
            event_type=f"{kwargs.get('scope_type')}.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id=str(kwargs.get("scope_key") or ""),
            scope_type=str(kwargs.get("scope_type") or ""),
            scope_key=str(kwargs.get("scope_key") or ""),
            dedupe_key=None,
            payload={},
            attempts=0,
            status="pending",
            priority=str(kwargs.get("priority") or "normal"),
            trace_id=str(kwargs.get("trace_id") or "") or None,
        )

    def read_model_refresh_is_active(self, *, tenant_id: str, scope_type: str, scope_key: str) -> bool:
        identity = (tenant_id, scope_type, scope_key)
        self.active_read_model_refresh_checks.append(identity)
        return identity in self.active_read_model_refreshes

    def read_model_refresh_is_fresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> bool:
        identity = (tenant_id, scope_type, scope_key)
        self.fresh_read_model_refresh_checks.append(identity)
        return identity in self.fresh_read_model_refreshes

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
            raise RuntimeError("workbench_relation_read_model_not_fresh: status=refreshing")

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
        self.assertEqual(queue.deferred_events, [("event-1", "worker-1", "workbench_relation_read_model_not_fresh: status=refreshing", 0.25)])
        self.assertEqual(queue.enqueued_read_model_refreshes, [])
        self.assertTrue(any(status == "deferred" for _worker_id, _kind, status, _payload in queue.heartbeats))

    def test_run_once_enqueues_dependency_refresh_before_deferring_not_fresh_event(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("pending_invoice.read_model.refresh").__dict__,
                "scope_type": "pending_invoice",
                "scope_key": "income:all:2026-04",
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
                event_types=["pending_invoice.read_model.refresh"],
                dependency_not_fresh_delay_seconds=4,
            ),
            handlers={"pending_invoice.read_model.refresh": fail_not_fresh},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.deferred_events, [("event-1", "worker-1", "bank_detail_read_model_not_fresh", 4)])
        self.assertEqual(len(queue.enqueued_read_model_refreshes), 1)
        dependency = queue.enqueued_read_model_refreshes[0]
        self.assertEqual(dependency["scope_type"], "bank_detail")
        self.assertEqual(dependency["scope_key"], "2026-04")
        self.assertEqual(dependency["reason"], "dependency_not_fresh")
        self.assertEqual(dependency["priority"], "high")
        self.assertEqual(dependency["trace_id"], "trace-dep-1")
        self.assertEqual(dependency["metadata"]["source_event_type"], "pending_invoice.read_model.refresh")
        self.assertEqual(dependency["metadata"]["source_scope_key"], "income:all:2026-04")
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertEqual(deferred_payloads[0]["dependency_refreshes"], [{"scope_type": "bank_detail", "scope_key": "2026-04"}])

    def test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("turnover_ledger.read_model.refresh").__dict__,
                "scope_type": "turnover_ledger",
                "scope_key": "all",
                "priority": "high",
            }
        )
        queue = FakeQueue(claimed)

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("bank_detail_read_model_not_fresh")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["turnover_ledger.read_model.refresh"]),
            handlers={"turnover_ledger.read_model.refresh": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.active_read_model_refresh_checks, [])
        self.assertEqual(queue.enqueued_read_model_refreshes, [])
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertNotIn("dependency_refreshes", deferred_payloads[0])

    def test_run_once_does_not_bump_dependency_refresh_when_scope_already_active(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("pending_invoice.read_model.refresh").__dict__,
                "tenant_id": "tenant-a",
                "scope_type": "pending_invoice",
                "scope_key": "expense:all:2026-04",
                "priority": "normal",
            }
        )
        queue = FakeQueue(claimed)
        queue.active_read_model_refreshes.add(("tenant-a", "bank_detail", "2026-04"))

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("bank_detail_read_model_not_fresh")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["pending_invoice.read_model.refresh"]),
            handlers={"pending_invoice.read_model.refresh": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.active_read_model_refresh_checks, [("tenant-a", "bank_detail", "2026-04")])
        self.assertEqual(queue.enqueued_read_model_refreshes, [])
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertEqual(
            deferred_payloads[0]["dependency_refreshes"],
            [{"scope_type": "bank_detail", "scope_key": "2026-04", "status": "already_active"}],
        )

    def test_run_once_does_not_bump_dependency_refresh_when_scope_already_fresh(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("pending_invoice.read_model.refresh").__dict__,
                "tenant_id": "tenant-a",
                "scope_type": "pending_invoice",
                "scope_key": "income:cash_income:2026-03",
                "priority": "high",
            }
        )
        queue = FakeQueue(claimed)
        queue.fresh_read_model_refreshes.add(("tenant-a", "bank_detail", "2026-03"))

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError("bank_detail_read_model_not_fresh")

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(worker_id="worker-1", event_types=["pending_invoice.read_model.refresh"]),
            handlers={"pending_invoice.read_model.refresh": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.active_read_model_refresh_checks, [("tenant-a", "bank_detail", "2026-03")])
        self.assertEqual(queue.fresh_read_model_refresh_checks, [("tenant-a", "bank_detail", "2026-03")])
        self.assertEqual(queue.enqueued_read_model_refreshes, [])
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertEqual(
            deferred_payloads[0]["dependency_refreshes"],
            [{"scope_type": "bank_detail", "scope_key": "2026-03", "status": "already_fresh"}],
        )

    def test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent(self) -> None:
        claimed = RuntimeQueueEvent(
            **{
                **event("workbench.read_model.refresh").__dict__,
                "tenant_id": "tenant-a",
                "scope_type": "workbench",
                "scope_key": "all",
                "priority": "normal",
                "trace_id": "trace-workbench-all",
            }
        )
        queue = FakeQueue(claimed)
        queue.fresh_read_model_refreshes.add(("tenant-a", "workbench", "2026-03"))

        def fail_not_fresh(_event: RuntimeQueueEvent) -> None:
            raise RuntimeError(
                "workbench_read_model_not_fresh: parent_generation_inconsistent "
                "parent_scope_keys=2026-03"
            )

        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["workbench.read_model.refresh"],
                dependency_not_fresh_delay_seconds=4,
                retry_delay_seconds=60,
            ),
            handlers={"workbench.read_model.refresh": fail_not_fresh},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        self.assertEqual(queue.failed_events, [])
        self.assertEqual(
            queue.deferred_events,
            [
                (
                    "event-1",
                    "worker-1",
                    "workbench_read_model_not_fresh: parent_generation_inconsistent parent_scope_keys=2026-03",
                    60.0,
                )
            ],
        )
        self.assertIn(("tenant-a", "workbench", "2026-03"), queue.active_read_model_refresh_checks)
        self.assertEqual(queue.fresh_read_model_refresh_checks, [])
        self.assertEqual(len(queue.enqueued_read_model_refreshes), 1)
        dependency = queue.enqueued_read_model_refreshes[0]
        self.assertEqual(dependency["scope_type"], "workbench")
        self.assertEqual(dependency["scope_key"], "2026-03")
        self.assertEqual(dependency["reason"], "dependency_not_fresh")
        self.assertEqual(dependency["priority"], "high")
        self.assertEqual(dependency["trace_id"], "trace-workbench-all")
        deferred_payloads = [payload for _worker_id, _kind, status, payload in queue.heartbeats if status == "deferred"]
        self.assertEqual(deferred_payloads[0]["delay_seconds"], 60.0)
        self.assertEqual(deferred_payloads[0]["dependency_refreshes"], [{"scope_type": "workbench", "scope_key": "2026-03"}])

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
                worker_instance="workbench",
                event_types=["runtime.test"],
            ),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.IDLE)
        self.assertTrue(queue.heartbeats)
        for _worker_id, _kind, _status, payload in queue.heartbeats:
            self.assertEqual(payload["worker_instance"], "workbench")

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
