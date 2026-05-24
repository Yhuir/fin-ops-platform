from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from fin_ops_platform.services.workbench_reconciliation_dirty_queue import (
    WorkbenchReconciliationDirtyQueue,
    WorkbenchReconciliationDirtyQueueOptions,
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 5, 25, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class WorkbenchReconciliationDirtyQueueTests(unittest.TestCase):
    def test_default_options_match_production_dirty_queue_contract(self) -> None:
        options = WorkbenchReconciliationDirtyQueueOptions()

        self.assertEqual(options.dirty_debounce_seconds, 60)
        self.assertEqual(options.lease_timeout_seconds, 600)
        self.assertEqual(options.retry_max_attempts, 5)
        self.assertEqual(options.retry_backoff_seconds, (60, 300, 900, 1800, 3600))

    def test_mark_dirty_expands_scope_month_window_and_debounces(self) -> None:
        clock = Clock()
        queue = WorkbenchReconciliationDirtyQueue(options=WorkbenchReconciliationDirtyQueueOptions(now=clock.now))

        marked = queue.mark_dirty_expanded(["2026-05"], reason="import_confirm", source_versions={"bank": 7})

        self.assertEqual(marked, ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07"])
        entries = queue.list_dirty_scopes()
        self.assertEqual(entries[0]["available_at"], datetime(2026, 5, 25, 9, 1, tzinfo=UTC))
        self.assertEqual(entries[0]["source_versions"], {"bank": 7})
        self.assertEqual(entries[0]["reasons"], ["import_confirm"])

    def test_claim_due_scopes_sets_lease_and_reclaims_stale_lease(self) -> None:
        clock = Clock()
        queue = WorkbenchReconciliationDirtyQueue(options=WorkbenchReconciliationDirtyQueueOptions(now=clock.now))
        queue.mark_dirty_expanded(["2026-05"], reason="unit")

        self.assertEqual(queue.claim_due_scopes(worker_id="worker-a", limit=10), [])
        clock.advance(60)
        self.assertEqual(queue.claim_due_scopes(worker_id="worker-a", limit=2), ["2026-03", "2026-04"])
        first = queue.get_dirty_scope("2026-03")
        self.assertEqual(first["status"], "processing")
        self.assertEqual(first["lease_owner"], "worker-a")
        self.assertEqual(first["lease_expires_at"], datetime(2026, 5, 25, 9, 11, tzinfo=UTC))

        self.assertNotIn("2026-03", queue.claim_due_scopes(worker_id="worker-b", limit=10))
        clock.advance(601)
        self.assertEqual(queue.claim_due_scopes(worker_id="worker-b", limit=1), ["2026-03"])
        self.assertEqual(queue.get_dirty_scope("2026-03")["lease_owner"], "worker-b")

    def test_complete_records_matching_run_lifecycle(self) -> None:
        clock = Clock()
        queue = WorkbenchReconciliationDirtyQueue(options=WorkbenchReconciliationDirtyQueueOptions(now=clock.now))
        queue.mark_dirty_expanded(["2026-05"], reason="unit")
        clock.advance(60)
        queue.claim_due_scopes(worker_id="worker-a", limit=1, request_id="request-1")
        clock.advance(3)

        queue.complete("2026-03", source_versions={"engine": "v1"})

        self.assertEqual(queue.get_dirty_scope("2026-03")["status"], "completed")
        self.assertEqual(
            queue.list_matching_runs(),
            [
                {
                    "scope_month": "2026-03",
                    "request_id": "request-1",
                    "started_at": datetime(2026, 5, 25, 9, 1, tzinfo=UTC),
                    "completed_at": datetime(2026, 5, 25, 9, 1, 3, tzinfo=UTC),
                    "failed_at": None,
                    "duration_ms": 3000,
                    "status": "completed",
                    "source_versions": {"engine": "v1"},
                    "error_summary": None,
                }
            ],
        )

    def test_fail_retries_with_configurable_backoff_until_max_attempts(self) -> None:
        clock = Clock()
        queue = WorkbenchReconciliationDirtyQueue(
            options=WorkbenchReconciliationDirtyQueueOptions(
                now=clock.now,
                retry_max_attempts=2,
                retry_backoff_seconds=(5, 20),
            )
        )
        queue.mark_dirty_expanded(["2026-05"], reason="unit")
        clock.advance(60)
        queue.claim_due_scopes(worker_id="worker-a", limit=1, request_id="request-1")

        queue.fail("2026-03", error="temporary")

        entry = queue.get_dirty_scope("2026-03")
        self.assertEqual(entry["status"], "retry")
        self.assertEqual(entry["attempt_count"], 1)
        self.assertEqual(entry["available_at"], datetime(2026, 5, 25, 9, 1, 5, tzinfo=UTC))
        self.assertEqual(queue.list_matching_runs()[0]["status"], "failed")
        self.assertEqual(queue.list_matching_runs()[0]["error_summary"], "temporary")

        clock.advance(5)
        queue.claim_due_scopes(worker_id="worker-a", limit=1, request_id="request-2")
        queue.fail("2026-03", error="permanent")

        entry = queue.get_dirty_scope("2026-03")
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["attempt_count"], 2)
        self.assertEqual(entry["last_error"], "permanent")


if __name__ == "__main__":
    unittest.main()
