from __future__ import annotations

import unittest
from time import sleep
from types import SimpleNamespace
from unittest.mock import Mock

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.runtime_worker_handlers import (
    ImportRuntimeProcessorFactory,
    WorkbenchMatchingWorkerFactory,
)
from fin_ops_platform.services.runtime_worker import (
    DEFAULT_RUNTIME_WORKER_POLL_INTERVAL_SECONDS,
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


class ImportRuntimeProcessorFactoryTests(unittest.TestCase):
    def test_controlled_replay_refuses_suspected_preview_before_persistence(self) -> None:
        state_store = SimpleNamespace(save_import_delta=Mock())
        replay_session = SimpleNamespace(
            status="preview_ready",
            files=[
                SimpleNamespace(
                    id="replay-file-1",
                    error_count=0,
                    suspected_duplicate_count=1,
                )
            ],
        )
        file_import_service = SimpleNamespace(
            replay_confirmed_session_files=Mock(return_value=(replay_session, 0))
        )
        factory = ImportRuntimeProcessorFactory(data_dir="/tmp", connection=Mock())
        factory._build_file_import_services_from_durable_state = Mock(
            return_value=(state_store, Mock(), file_import_service)
        )

        with self.assertRaisesRegex(RuntimeError, "refusing confirmation"):
            factory.replay_confirmed_file_import_session(
                source_session_id="source-session-1",
                selected_file_ids=["source-file-1"],
                operator_id="repair-operator",
            )

        state_store.save_import_delta.assert_not_called()


class WorkbenchMatchingWorkerFactoryTests(unittest.TestCase):
    def test_build_reads_only_settings_instead_of_full_import_snapshot(self) -> None:
        state_store = SimpleNamespace(
            load_app_settings=Mock(return_value={}),
            load_bank_transaction_categories=Mock(return_value={}),
            load_imports_snapshot=Mock(
                side_effect=AssertionError("matching startup must not load all imports")
            ),
        )
        factory = WorkbenchMatchingWorkerFactory(data_dir="/tmp", connection=Mock())
        factory._state_store = Mock(return_value=state_store)

        worker = factory.build_dirty_scope_worker(
            heartbeat_recorder=Mock(),
            worker_id="matching-test",
            poll_interval_seconds=0.25,
            batch_size=10,
            lease_seconds=600,
            retry_delay_seconds=60,
            max_iterations=1,
        )

        source_versions = worker._source_versions_provider()

        self.assertEqual(source_versions["bank_auto_tag_rules_version"], 1)
        state_store.load_app_settings.assert_called_once_with()
        state_store.load_imports_snapshot.assert_not_called()


class FakeQueue:
    def __init__(self, claimed: RuntimeQueueEvent | None) -> None:
        self.claimed = claimed
        self.claim_calls: list[tuple[str, list[str] | None, int]] = []
        self.claim_filter_calls: list[dict[str, object]] = []
        self.completed: list[tuple[str, str, dict[str, object] | None]] = []
        self.acked: list[tuple[str, str, dict[str, object] | None]] = []
        self.failed: list[tuple[str, str, str, bool, int]] = []
        self.failed_events: list[tuple[str, str, str, bool, int, int]] = []
        self.released_events: list[tuple[str, str, str]] = []
        self.deferred_events: list[tuple[str, str, str, int]] = []
        self.heartbeats: list[tuple[str, str, str, object]] = []
        self.statement_timeouts: list[int | None] = []

    def claim_next(
        self,
        worker_id: str,
        event_types=None,
        lock_timeout_seconds: int = 300,
        **filters,
    ):
        self.claim_calls.append((worker_id, list(event_types) if event_types is not None else None, lock_timeout_seconds))
        self.claim_filter_calls.append(dict(filters))
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

    def claim_next(self, worker_id: str, event_types=None, lock_timeout_seconds: int = 300, **filters):
        self.claim_calls.append((worker_id, list(event_types) if event_types is not None else None, lock_timeout_seconds))
        self.claim_filter_calls.append(dict(filters))
        return self.claimed_events.pop(0) if self.claimed_events else None


class RuntimeWorkerTests(unittest.TestCase):
    def test_default_poll_interval_is_fast_enough_for_runtime_slo(self) -> None:
        self.assertEqual(DEFAULT_RUNTIME_WORKER_POLL_INTERVAL_SECONDS, 0.05)
        self.assertEqual(RuntimeWorkerConfig().poll_interval_seconds, 0.05)
        self.assertEqual(RuntimeWorkerConfig().heartbeat_min_interval_seconds, 1.0)

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
                worker_id="host-import",
                worker_kind="import-job",
                worker_instance="import",
                event_types=["runtime.test"],
            ),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        result = worker.run_once()

        self.assertEqual(result, RuntimeWorkerResult.IDLE)
        self.assertTrue(queue.heartbeats)
        for _worker_id, _kind, _status, payload in queue.heartbeats:
            self.assertEqual(payload["worker_instance"], "import")

    def test_fast_empty_polls_throttle_idle_heartbeat_writes(self) -> None:
        queue = FakeQueue(None)
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                poll_interval_seconds=0.05,
                heartbeat_min_interval_seconds=1.0,
            ),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)

        self.assertEqual(len(queue.claim_calls), 3)
        self.assertEqual([status for _worker_id, _kind, status, _payload in queue.heartbeats], ["idle"])

    def test_run_once_passes_claim_scope_filters_to_queue(self) -> None:
        queue = FakeQueue(None)
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                claim_scope_keys=["all"],
                exclude_claim_scope_keys=["2026-02"],
            ),
            handlers={
                "runtime.test": lambda claimed: {
                    "handled": claimed.event_id
                }
            },
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)

        self.assertEqual(
            queue.claim_filter_calls[0],
            {"scope_keys": ["all"], "exclude_scope_keys": ["2026-02"]},
        )

    def test_event_processing_heartbeats_bypass_idle_throttle(self) -> None:
        queue = FakeQueue(None)
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_id="worker-1",
                event_types=["runtime.test"],
                heartbeat_min_interval_seconds=60.0,
            ),
            handlers={"runtime.test": lambda claimed: {"handled": claimed.event_id}},
        )

        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)
        queue.claimed = event()
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)

        self.assertEqual(
            [status for _worker_id, _kind, status, _payload in queue.heartbeats],
            ["idle", "processing", "idle"],
        )
        self.assertEqual(queue.acked[0][0:2], ("event-1", "worker-1"))

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
