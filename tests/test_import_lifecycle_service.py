from __future__ import annotations

import unittest
from contextlib import contextmanager

from fin_ops_platform.services.import_lifecycle_service import ImportLifecycleService
from fin_ops_platform.services.postgres_repositories.import_lifecycle import PostgresImportLifecycleRepository


class FakeLifecycleRepository:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def list_events(self, *, page: int, page_size: int):
        return self.rows, len(self.rows)

    def list_active_sessions(self, *, imported_by: str, mode: str | None):
        return self.rows


class FakeDiscardTransaction:
    def __init__(self, *, rows: list[dict[str, object]], active_job: dict[str, object] | None = None) -> None:
        self.rows = rows
        self.active_job = active_job
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_sql = ""
        self.fetch_one_sql = ""

    def fetch_all(self, sql: str, _params: tuple[object, ...]):
        self.fetch_all_sql = sql
        return self.rows

    def fetch_one(self, sql: str, _params: tuple[object, ...]):
        self.fetch_one_sql = sql
        return self.active_job

    def execute(self, sql: str, params: tuple[object, ...]):
        self.executed.append((sql, params))
        return 1


class FakeDiscardConnection:
    def __init__(self, transaction: FakeDiscardTransaction) -> None:
        self.value = transaction

    @contextmanager
    def transaction(self):
        yield self.value


class RecordingLifecycleConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def fetch_one(self, sql: str, _params: tuple[object, ...] | None = None):
        self.queries.append(sql)
        return {"total": 0}

    def fetch_all(self, sql: str, _params: tuple[object, ...]):
        self.queries.append(sql)
        return []


class ImportLifecycleServiceTests(unittest.TestCase):
    def test_maps_durable_lifecycle_states_and_pagination(self) -> None:
        rows = [
            {"event_id": "preview", "batch_status": "pending", "file_status": "preview_ready"},
            {"event_id": "queued", "batch_status": "pending", "job_status": "pending"},
            {"event_id": "running", "batch_status": "pending", "job_status": "processing"},
            {"event_id": "done", "batch_status": "completed", "file_status": "confirmed"},
            {"event_id": "failed", "batch_status": "pending", "job_status": "failed"},
            {"event_id": "discarded", "batch_status": "reverted", "file_status": "reverted"},
            {"event_id": "broken", "batch_status": "pending", "job_status": "succeeded"},
        ]
        payload = ImportLifecycleService(FakeLifecycleRepository(rows)).list_events(page=1, page_size=3)  # type: ignore[arg-type]

        self.assertEqual(
            [row["status"] for row in payload["rows"]],
            ["awaiting_confirmation", "queued", "processing", "succeeded", "failed", "discarded", "inconsistent"],
        )
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 3, "total": 7, "total_pages": 3})

    def test_active_session_with_confirmable_file_remains_recoverable(self) -> None:
        service = ImportLifecycleService(
            FakeLifecycleRepository(
                [{
                    "session_id": "session-1",
                    "imported_by": "user-1",
                    "file_count": 2,
                    "session_status": "preview_ready_with_errors",
                    "has_confirmable_file": True,
                }]
            )  # type: ignore[arg-type]
        )

        sessions = service.list_active_sessions(imported_by="user-1", mode="invoice")

        self.assertEqual(sessions[0]["status"], "awaiting_confirmation")

    def test_postgres_discard_is_atomic_owned_and_rejects_active_job(self) -> None:
        rows = [{"id": "file-1", "status": "preview_ready", "imported_by": "user-1", "batch_id": "batch-1"}]
        transaction = FakeDiscardTransaction(rows=rows)
        repository = PostgresImportLifecycleRepository(FakeDiscardConnection(transaction))

        self.assertEqual(repository.discard_preview_session(session_id="session-1", imported_by="user-1"), 1)
        self.assertEqual(len(transaction.executed), 2)
        self.assertIn("import_job.id::text as import_job_id", transaction.fetch_one_sql)
        self.assertNotIn("import_job.import_job_id", transaction.fetch_one_sql)
        self.assertIn("import_file.status <> 'deleted'", transaction.fetch_all_sql)

        with self.assertRaises(PermissionError):
            PostgresImportLifecycleRepository(
                FakeDiscardConnection(FakeDiscardTransaction(rows=rows))
            ).discard_preview_session(session_id="session-1", imported_by="user-2")
        with self.assertRaises(ValueError):
            PostgresImportLifecycleRepository(
                FakeDiscardConnection(FakeDiscardTransaction(rows=rows, active_job={"status": "pending"}))
            ).discard_preview_session(session_id="session-1", imported_by="user-1")

    def test_postgres_queries_use_import_jobs_primary_key_column(self) -> None:
        connection = RecordingLifecycleConnection()
        repository = PostgresImportLifecycleRepository(connection)

        repository.list_events()
        repository.list_active_sessions(imported_by="user-1", mode="invoice")

        job_queries = [sql for sql in connection.queries if "job.import_jobs" in sql]
        self.assertEqual(len(job_queries), 2)
        self.assertTrue(all("import_job.id::text as import_job_id" in sql for sql in job_queries))
        self.assertTrue(all("import_job.import_job_id" not in sql for sql in job_queries))
        history_query = job_queries[0]
        self.assertEqual(history_query.count("left join lateral"), 2)
        self.assertIn("limit %s offset %s", history_query)


if __name__ == "__main__":
    unittest.main()
