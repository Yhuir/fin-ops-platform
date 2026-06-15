from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)


class RecordingDirtyQueue:
    def __init__(
        self,
        claimed_scopes: list[str] | None = None,
        stale_completed_scopes: list[str] | None = None,
    ) -> None:
        self.claimed_scopes = list(claimed_scopes or [])
        self.stale_completed_scopes = list(stale_completed_scopes or [])
        self.events: list[str] = []
        self.mark_stale_calls: list[dict[str, object]] = []
        self.claim_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.fail_calls: list[dict[str, object]] = []

    def mark_stale_completed_scopes(self, **kwargs) -> list[str]:
        self.events.append("mark_stale_completed_scopes")
        self.mark_stale_calls.append(dict(kwargs))
        return list(self.stale_completed_scopes)

    def claim_due_scopes(self, **kwargs) -> list[str]:
        self.events.append("claim_due_scopes")
        self.claim_calls.append(dict(kwargs))
        return list(self.claimed_scopes)

    def complete(self, scope_month: str, **kwargs) -> None:
        self.complete_calls.append({"scope_month": scope_month, **kwargs})

    def fail(self, scope_month: str, **kwargs) -> None:
        self.fail_calls.append({"scope_month": scope_month, **kwargs})


class RecordingOrchestrator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.run_calls: list[dict[str, object]] = []

    def run(self, **kwargs) -> dict[str, object]:
        self.run_calls.append(dict(kwargs))
        if self.fail:
            raise RuntimeError("matching failed")
        return {"candidate_count": 3, "processed_months": list(kwargs["changed_scope_months"])}


class RecordingHeartbeatRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def record_worker_heartbeat(
        self,
        worker_id: str,
        worker_kind: str,
        status: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.calls.append(
            {
                "worker_id": worker_id,
                "worker_kind": worker_kind,
                "status": status,
                "payload": dict(payload or {}),
            }
        )


class WorkbenchMatchingDirtyScopeWorkerTests(unittest.TestCase):
    def _worker(
        self,
        *,
        dirty_queue: RecordingDirtyQueue,
        orchestrator: RecordingOrchestrator | None = None,
        heartbeat_recorder: RecordingHeartbeatRecorder | None = None,
        sleep_calls: list[float] | None = None,
        max_iterations: int | None = None,
        source_versions: dict[str, object] | None = None,
    ) -> tuple[WorkbenchMatchingDirtyScopeWorker, RecordingHeartbeatRecorder, list[float]]:
        recorder = heartbeat_recorder or RecordingHeartbeatRecorder()
        sleeps = sleep_calls if sleep_calls is not None else []
        worker = WorkbenchMatchingDirtyScopeWorker(
            dirty_queue=dirty_queue,
            matching_orchestrator=orchestrator or RecordingOrchestrator(),
            source_versions_provider=lambda: dict(source_versions or {"rules": "v1"}),
            heartbeat_recorder=recorder,
            config=WorkbenchMatchingDirtyScopeWorkerConfig(
                worker_id="worker-a",
                poll_interval_seconds=0.5,
                batch_size=7,
                lease_seconds=300,
                retry_delay_seconds=45,
                max_iterations=max_iterations,
                request_id_factory=lambda: "request-a",
            ),
            sleep=sleeps.append,
        )
        return worker, recorder, sleeps

    def test_run_once_records_idle_heartbeat_when_no_due_scopes(self) -> None:
        dirty_queue = RecordingDirtyQueue()
        worker, recorder, _ = self._worker(dirty_queue=dirty_queue)

        summary = worker.run_once()

        self.assertEqual(summary["processed_months"], [])
        self.assertEqual(dirty_queue.claim_calls[0]["worker_id"], "worker-a")
        self.assertEqual(dirty_queue.claim_calls[0]["limit"], 7)
        self.assertEqual(dirty_queue.claim_calls[0]["lease_seconds"], 300)
        self.assertEqual(dirty_queue.events, ["mark_stale_completed_scopes", "claim_due_scopes"])
        self.assertEqual([call["status"] for call in recorder.calls], ["polling", "idle"])
        self.assertEqual(recorder.calls[-1]["worker_kind"], "workbench-matching")

    def test_run_once_marks_stale_completed_scopes_before_claiming_due_scopes(self) -> None:
        dirty_queue = RecordingDirtyQueue(["2026-01"], stale_completed_scopes=["2026-01"])
        orchestrator = RecordingOrchestrator()
        worker, recorder, _ = self._worker(
            dirty_queue=dirty_queue,
            orchestrator=orchestrator,
            source_versions={"workbench_matching_rules_version": "v2"},
        )

        summary = worker.run_once()

        self.assertEqual(dirty_queue.events[:2], ["mark_stale_completed_scopes", "claim_due_scopes"])
        self.assertEqual(dirty_queue.mark_stale_calls[0]["source_versions"], {"workbench_matching_rules_version": "v2"})
        self.assertEqual(dirty_queue.mark_stale_calls[0]["reason"], "matching_source_versions_changed")
        self.assertEqual(dirty_queue.mark_stale_calls[0]["limit"], 7)
        self.assertEqual(summary["stale_completed_scope_months"], ["2026-01"])
        self.assertEqual(orchestrator.run_calls[0]["changed_scope_months"], ["2026-01"])
        self.assertEqual(recorder.calls[0]["payload"]["stale_completed_scope_count"], 1)

    def test_run_once_records_processing_then_completes_scope_and_returns_idle(self) -> None:
        dirty_queue = RecordingDirtyQueue(["2026-01"])
        orchestrator = RecordingOrchestrator()
        worker, recorder, _ = self._worker(dirty_queue=dirty_queue, orchestrator=orchestrator)

        summary = worker.run_once()

        self.assertEqual([call["status"] for call in recorder.calls], ["polling", "processing", "idle"])
        self.assertEqual(orchestrator.run_calls[0]["changed_scope_months"], ["2026-01"])
        self.assertEqual(orchestrator.run_calls[0]["reason"], "dirty_scope_retry")
        self.assertEqual(dirty_queue.complete_calls[0]["scope_month"], "2026-01")
        self.assertEqual(dirty_queue.complete_calls[0]["source_versions"], {"rules": "v1"})
        self.assertEqual(dirty_queue.complete_calls[0]["worker_id"], "worker-a")
        self.assertEqual(dirty_queue.complete_calls[0]["request_id"], "request-a:2026-01")
        self.assertEqual(summary["processed_months"], ["2026-01"])
        self.assertEqual(summary["candidate_count"], 3)

    def test_run_once_fails_scope_and_records_failed_heartbeat_on_exception(self) -> None:
        dirty_queue = RecordingDirtyQueue(["2026-02"])
        orchestrator = RecordingOrchestrator(fail=True)
        worker, recorder, _ = self._worker(dirty_queue=dirty_queue, orchestrator=orchestrator)

        summary = worker.run_once()

        self.assertEqual([call["status"] for call in recorder.calls], ["polling", "processing", "failed"])
        self.assertEqual(dirty_queue.fail_calls[0]["scope_month"], "2026-02")
        self.assertEqual(dirty_queue.fail_calls[0]["error"], "matching failed")
        self.assertEqual(dirty_queue.fail_calls[0]["retry_delay_seconds"], 45)
        self.assertEqual(dirty_queue.fail_calls[0]["worker_id"], "worker-a")
        self.assertEqual(dirty_queue.fail_calls[0]["request_id"], "request-a:2026-02")
        self.assertEqual(summary["failed_months"], ["2026-02"])

    def test_run_forever_stops_at_max_iterations_without_sleeping_after_final_iteration(self) -> None:
        dirty_queue = RecordingDirtyQueue()
        worker, _, sleeps = self._worker(dirty_queue=dirty_queue, max_iterations=1)

        worker.run_forever()

        self.assertEqual(len(dirty_queue.claim_calls), 1)
        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
