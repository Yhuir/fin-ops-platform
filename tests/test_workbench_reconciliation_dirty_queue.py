from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
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


class RepositoryTransaction:
    def __init__(self, parent: "RepositoryRecordingConnection") -> None:
        self.parent = parent

    def __enter__(self) -> "RepositoryTransaction":
        self.parent.transaction_enters += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.parent.transaction_exits += 1

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return self.parent.fetch_all(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        return self.parent.fetch_one(sql, params)

    def execute(self, sql: str, params: tuple = ()) -> int:
        return self.parent.execute(sql, params)


class RepositoryRecordingConnection:
    def __init__(self) -> None:
        self.transaction_enters = 0
        self.transaction_exits = 0
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []
        self.claim_rows = [
            {
                "scope_month": "2026-03",
                "request_id": "request-1:2026-03",
                "source_versions": {"bank": 1},
            }
        ]
        self.scope_update_row = {
            "request_id": "request-1:2026-03",
            "duration_ms": 1200,
            "source_versions": {"bank": 1},
        }

    def transaction(self) -> RepositoryTransaction:
        return RepositoryTransaction(self)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
        if "update job.workbench_matching_dirty_scopes" in self.fetch_all_calls[-1][0]:
            return list(self.claim_rows)
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        return dict(self.scope_update_row)

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.execute_calls.append((" ".join(sql.lower().split()), params))
        return 1


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

        queue.complete(
            "2026-03",
            source_versions={"engine": "v1"},
            worker_id="worker-a",
            request_id="request-1:2026-03",
        )

        self.assertEqual(queue.get_dirty_scope("2026-03")["status"], "completed")
        self.assertEqual(
            queue.list_matching_runs(),
            [
                {
                    "scope_month": "2026-03",
                    "request_id": "request-1:2026-03",
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

        queue.fail("2026-03", error="temporary", worker_id="worker-a", request_id="request-1:2026-03")

        entry = queue.get_dirty_scope("2026-03")
        self.assertEqual(entry["status"], "retry")
        self.assertEqual(entry["attempt_count"], 1)
        self.assertEqual(entry["available_at"], datetime(2026, 5, 25, 9, 1, 5, tzinfo=UTC))
        self.assertEqual(queue.list_matching_runs()[0]["status"], "failed")
        self.assertEqual(queue.list_matching_runs()[0]["error_summary"], "temporary")

        clock.advance(5)
        queue.claim_due_scopes(worker_id="worker-a", limit=1, request_id="request-2")
        queue.fail("2026-03", error="permanent", worker_id="worker-a", request_id="request-2:2026-03")

        entry = queue.get_dirty_scope("2026-03")
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["attempt_count"], 2)
        self.assertEqual(entry["last_error"], "permanent")

    def test_complete_and_fail_require_matching_active_lease_identity(self) -> None:
        clock = Clock()
        queue = WorkbenchReconciliationDirtyQueue(options=WorkbenchReconciliationDirtyQueueOptions(now=clock.now))
        queue.mark_dirty_expanded(["2026-05"], reason="unit")
        clock.advance(60)
        queue.claim_due_scopes(worker_id="worker-a", limit=1, request_id="request-1")

        with self.assertRaisesRegex(ValueError, "worker_id"):
            queue.complete("2026-03", source_versions={"engine": "v1"})
        with self.assertRaisesRegex(ValueError, "request_id"):
            queue.fail("2026-03", error="temporary", worker_id="worker-a")
        with self.assertRaisesRegex(RuntimeError, "active lease"):
            queue.complete(
                "2026-03",
                source_versions={"engine": "v1"},
                worker_id="worker-b",
                request_id="request-1:2026-03",
            )
        with self.assertRaisesRegex(RuntimeError, "active lease"):
            queue.fail(
                "2026-03",
                error="temporary",
                worker_id="worker-a",
                request_id="request-other:2026-03",
            )

        entry = queue.get_dirty_scope("2026-03")
        self.assertEqual(entry["status"], "processing")
        self.assertEqual(entry["lease_owner"], "worker-a")
        self.assertEqual(entry["request_id"], "request-1:2026-03")

    def test_repository_claim_wraps_scope_claim_and_run_audit_in_one_transaction(self) -> None:
        connection = RepositoryRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        with patch("fin_ops_platform.services.postgres_repositories.read_models.jsonb", side_effect=lambda value: value):
            claimed = repository.claim_workbench_matching_dirty_scopes(
                tenant_id="tenant-a",
                worker_id="worker-a",
                limit=1,
                lease_seconds=600,
                request_id="request-1",
            )

        self.assertEqual(claimed, ["2026-03"])
        self.assertEqual(connection.transaction_enters, 1)
        self.assertEqual(connection.transaction_exits, 1)
        self.assertEqual(len(connection.fetch_all_calls), 1)
        self.assertIn("for update skip locked", connection.fetch_all_calls[0][0])
        self.assertEqual(len(connection.execute_calls), 1)
        run_sql, run_params = connection.execute_calls[0]
        self.assertIn("insert into app.matching_runs", run_sql)
        self.assertIn("tenant_id", run_sql)
        self.assertIn("on conflict (tenant_id, request_id)", run_sql)
        self.assertIn("tenant-a", run_params)

    def test_repository_complete_and_fail_require_active_lease_identity(self) -> None:
        connection = RepositoryRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        with patch("fin_ops_platform.services.postgres_repositories.read_models.jsonb", side_effect=lambda value: value):
            repository.complete_workbench_matching_dirty_scope(
                tenant_id="tenant-a",
                scope_month="2026-03",
                source_versions={"engine": "v1"},
                worker_id="worker-a",
                request_id="request-1:2026-03",
            )
        complete_scope_sql, complete_scope_params = connection.fetch_one_calls[-1]
        complete_run_sql, complete_run_params = connection.execute_calls[-1]
        self.assertIn("status = 'processing'", complete_scope_sql)
        self.assertIn("lease_owner = %s", complete_scope_sql)
        self.assertIn("request_id = %s", complete_scope_sql)
        self.assertNotIn("is null or lease_owner", complete_scope_sql)
        self.assertNotIn("is null or request_id", complete_scope_sql)
        self.assertNotIn("to_char(scope_month", complete_scope_sql)
        self.assertIn("tenant_id = %s", complete_run_sql)
        self.assertIn("worker-a", complete_scope_params)
        self.assertIn("request-1:2026-03", complete_scope_params)
        self.assertIn("tenant-a", complete_run_params)

        with patch("fin_ops_platform.services.postgres_repositories.read_models.jsonb", side_effect=lambda value: value):
            repository.fail_workbench_matching_dirty_scope(
                tenant_id="tenant-a",
                scope_month="2026-03",
                error="temporary",
                retry_delay_seconds=None,
                retry_max_attempts=5,
                retry_backoff_seconds=[60, 300, 900],
                worker_id="worker-a",
                request_id="request-1:2026-03",
            )
        fail_scope_sql, fail_scope_params = connection.fetch_one_calls[-1]
        fail_run_sql, fail_run_params = connection.execute_calls[-1]
        self.assertIn("status = 'processing'", fail_scope_sql)
        self.assertIn("lease_owner = %s", fail_scope_sql)
        self.assertIn("request_id = %s", fail_scope_sql)
        self.assertNotIn("is null or lease_owner", fail_scope_sql)
        self.assertNotIn("is null or request_id", fail_scope_sql)
        self.assertIn("attempt_count + 1 = 2 then 300", fail_scope_sql)
        self.assertNotIn("to_char(scope_month", fail_scope_sql)
        self.assertIn("tenant_id = %s", fail_run_sql)
        self.assertIn("worker-a", fail_scope_params)
        self.assertIn("request-1:2026-03", fail_scope_params)
        self.assertIn("tenant-a", fail_run_params)


if __name__ == "__main__":
    unittest.main()
