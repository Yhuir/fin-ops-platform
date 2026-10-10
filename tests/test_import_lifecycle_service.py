from __future__ import annotations

import unittest
from contextlib import contextmanager

from fin_ops_platform.services.import_lifecycle_service import ImportLifecycleService
from fin_ops_platform.services.postgres_repositories.import_lifecycle import PostgresImportLifecycleRepository


class FakeLifecycleRepository:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def list_events(self, **query):
        self.query = query
        return self.rows, len(self.rows)

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
        return [{"event_id": None, "total": 0}]


class ImportLifecycleServiceTests(unittest.TestCase):
    def test_maps_durable_lifecycle_states_and_pagination(self) -> None:
        rows = [
            {"display_status": "awaiting_confirmation", "event_id": "preview", "batch_status": "pending", "file_status": "preview_ready"},
            {"display_status": "queued", "event_id": "queued", "batch_status": "pending", "job_status": "pending"},
            {"display_status": "processing", "event_id": "running", "batch_status": "pending", "job_status": "processing"},
            {"display_status": "succeeded", "event_id": "done", "batch_status": "completed", "file_status": "confirmed"},
            {"display_status": "failed", "event_id": "failed", "batch_status": "pending", "job_status": "failed"},
            {"display_status": "discarded", "event_id": "discarded", "batch_status": "reverted", "file_status": "reverted"},
            {"display_status": "inconsistent", "event_id": "broken", "batch_status": "pending", "job_status": "succeeded"},
        ]
        payload = ImportLifecycleService(FakeLifecycleRepository(rows)).list_events(page=1, page_size=3)  # type: ignore[arg-type]

        self.assertEqual(
            [row["status"] for row in payload["rows"]],
            ["awaiting_confirmation", "queued", "processing", "succeeded", "failed", "discarded", "inconsistent"],
        )
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 3, "total": 7, "total_pages": 3})

    def test_validates_history_filters_and_inclusive_business_dates(self):
        repository = FakeLifecycleRepository([])
        service = ImportLifecycleService(repository)
        service.list_events(search=" bank%_.xlsx ", start_date="2026-10-10", end_date="2026-10-10")
        self.assertEqual(repository.query["search"], "bank%_.xlsx")
        self.assertEqual(repository.query["start_at"].isoformat(), "2026-10-10T00:00:00+08:00")
        self.assertEqual(repository.query["end_at"].isoformat(), "2026-10-11T00:00:00+08:00")
        for query in ({"page": 0}, {"page_size": 101}, {"batch_type": "fake"}, {"status": "fake"},
                      {"start_date": "20261010"}, {"start_date": "2026-10-11", "end_date": "2026-10-10"},
                      {"search": "x" * 201}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                service.list_events(**query)
        with self.assertRaises(KeyError):
            service.detail_event("missing")

    def test_postgres_discard_is_atomic_owned_and_rejects_active_job(self) -> None:
        rows = [{"id": "file-1", "status": "preview_ready", "imported_by": "user-1", "batch_id": "batch-1"}]
        transaction = FakeDiscardTransaction(rows=rows)
        repository = PostgresImportLifecycleRepository(FakeDiscardConnection(transaction))

        self.assertEqual(repository.discard_preview_session(session_id="session-1", imported_by="user-1"), 1)
        self.assertEqual(len(transaction.executed), 2)
        self.assertIn("raw_payload = jsonb_set", transaction.executed[0][0])
        self.assertIn("to_jsonb('reverted'::text)", transaction.executed[0][0])
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

        job_queries = [sql for sql in connection.queries if "job.import_jobs" in sql]
        self.assertEqual(len(job_queries), 1)
        self.assertTrue(all("import_job.id::text as import_job_id" in sql for sql in job_queries))
        self.assertTrue(all("import_job.import_job_id" not in sql for sql in job_queries))
        history_query = job_queries[0]
        self.assertEqual(history_query.count("left join lateral"), 4)
        self.assertIn("batch_row.decision = 'created'", history_query)
        self.assertIn("limit %s offset %s", history_query)
        self.assertIn("select count(*)::bigint as total from filtered", history_query)


if __name__ == "__main__":
    unittest.main()
