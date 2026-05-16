from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from fin_ops_platform.services.worker_task_postgres_repository import PostgresWorkerTaskRepository
from fin_ops_platform.services.worker_task_protocol import WorkerDelivery, WorkerTaskRecord
from scripts.tools import job_dead_letter_replay


FIXED_NOW = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)


class RecordingCursor:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.statements.append((" ".join(sql.split()), params))

    def fetchone(self) -> dict[str, object] | None:
        return self.row

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class RecordingConnection:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.cursor_obj = RecordingCursor(row)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, *, row_factory=None) -> RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class WorkerTaskPostgresRepositoryTests(unittest.TestCase):
    def test_load_task_for_update_locks_row_and_maps_record(self) -> None:
        connection = RecordingConnection(
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "task_type": "read_model.rebuild",
                "status": "queued",
                "idempotency_key": "read_model.rebuild:workbench:2026-05:v42",
                "attempt_count": 1,
                "max_attempts": 3,
            }
        )
        repository = PostgresWorkerTaskRepository(lambda: connection)

        task = repository.load_task_for_update("22222222-2222-4222-8222-222222222222")

        self.assertEqual(
            task,
            WorkerTaskRecord(
                task_id="22222222-2222-4222-8222-222222222222",
                task_type="read_model.rebuild",
                status="queued",
                idempotency_key="read_model.rebuild:workbench:2026-05:v42",
                attempt_count=1,
                max_attempts=3,
            ),
        )
        self.assertIn("for update", connection.cursor_obj.statements[0][0].lower())

    def test_create_attempt_records_delivery_metadata_inside_lease_transaction(self) -> None:
        connection = RecordingConnection()
        repository = PostgresWorkerTaskRepository(lambda: connection)
        task = WorkerTaskRecord(
            task_id="22222222-2222-4222-8222-222222222222",
            task_type="read_model.rebuild",
            status="queued",
            idempotency_key="read_model.rebuild:workbench:2026-05:v42",
            attempt_count=0,
            max_attempts=3,
        )

        attempt_id = repository.create_attempt(
            task=task,
            attempt_no=1,
            worker_id="worker-1",
            delivery=WorkerDelivery(nats_stream="FINOPS_JOBS", nats_consumer="read-model-workers", nats_sequence=42),
            started_at=FIXED_NOW,
        )

        self.assertTrue(attempt_id)
        insert_sql, params = connection.cursor_obj.statements[0]
        self.assertIn("insert into job.worker_attempts", insert_sql.lower())
        self.assertIn("FINOPS_JOBS", params)
        self.assertIn("read-model-workers", params)
        self.assertIn(42, params)

    def test_mark_dead_lettered_updates_task_attempt_and_dead_letter_atomically(self) -> None:
        connection = RecordingConnection()
        repository = PostgresWorkerTaskRepository(lambda: connection)

        repository.mark_dead_lettered(
            task_id="22222222-2222-4222-8222-222222222222",
            attempt_id="33333333-3333-4333-8333-333333333333",
            error_code="OA_SOURCE_UNAVAILABLE",
            error_summary="OA source unavailable",
            error_detail={"host": "oa"},
            payload={"task_id": "22222222-2222-4222-8222-222222222222"},
            finished_at=FIXED_NOW,
        )

        combined_sql = " ".join(statement for statement, _ in connection.cursor_obj.statements).lower()
        self.assertIn("update job.worker_attempts", combined_sql)
        self.assertIn("update job.worker_tasks", combined_sql)
        self.assertIn("insert into job.dead_letters", combined_sql)
        self.assertEqual(connection.commits, 1)

    def test_record_heartbeat_updates_attempt_and_worker_heartbeat_fact(self) -> None:
        connection = RecordingConnection()
        repository = PostgresWorkerTaskRepository(lambda: connection)

        repository.record_heartbeat(
            task_id="22222222-2222-4222-8222-222222222222",
            attempt_id="33333333-3333-4333-8333-333333333333",
            worker_id="worker-1",
            heartbeat_at=FIXED_NOW,
        )

        combined_sql = " ".join(statement for statement, _ in connection.cursor_obj.statements).lower()
        self.assertIn("update job.worker_attempts", combined_sql)
        self.assertIn("insert into job.worker_heartbeats", combined_sql)
        self.assertIn("on conflict", combined_sql)

    def test_dead_letter_replay_creates_new_outbox_and_records_audit(self) -> None:
        source = job_dead_letter_replay.build_replay_sql("outbox")

        self.assertIn("insert into job.outbox_events", source.lower())
        self.assertIn("insert into audit.events", source.lower())
        self.assertNotIn("set status = 'retrying'", source.lower())
        UUID("11111111-1111-4111-8111-111111111111")


if __name__ == "__main__":
    unittest.main()
