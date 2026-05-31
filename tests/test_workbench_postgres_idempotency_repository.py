from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.workbench_idempotency import (
    InMemoryWorkbenchIdempotencyRepository,
    WorkbenchIdempotencyRecord,
    WorkbenchIdempotencyReservation,
)


def _json_obj(value: object) -> object:
    return getattr(value, "obj", value)


def _record_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tenant_id": "default",
        "actor_id": "finance-1",
        "action_name": "confirm_link",
        "idempotency_key": "confirm:idem-1",
        "request_fingerprint": "fp:confirm:idem-1",
        "status": "committed",
        "request_payload": {"case_id": "CASE-1"},
        "response_payload": {"case_id": "CASE-1"},
        "source_versions": {"workbench:2026-05": 7},
        "outbox_event_ids": ["event-1"],
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "expires_at": None,
    }
    base.update(overrides)
    return base


class _RecordingSqlExecutor:
    def __init__(self, rows: list[dict[str, object] | None] | None = None) -> None:
        self.rows = list(rows or [])
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.transaction_opened = False

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if self.rows:
            return self.rows.pop(0)
        return None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        normalized = " ".join(sql.lower().split())
        self.execute_calls.append((normalized, params))
        return 1

    def transaction(self) -> object:
        self.transaction_opened = True
        raise AssertionError("idempotency repository methods must use the supplied transaction")


class _QueueRepository:
    pass


class _PostgresStateStore:
    storage_backend = "postgres"

    def __init__(self, connection: object) -> None:
        self._connection = connection


class WorkbenchPostgresIdempotencyRepositoryTests(unittest.TestCase):
    def test_get_committed_or_reserved_maps_postgres_row_to_record(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
            PostgresWorkbenchIdempotencyRepository,
        )

        executor = _RecordingSqlExecutor(rows=[_record_row()])
        repository = PostgresWorkbenchIdempotencyRepository(executor)

        record = repository.get_committed_or_reserved(
            tenant_id="default",
            actor_id="finance-1",
            idempotency_key="confirm:idem-1",
        )

        self.assertIsInstance(record, WorkbenchIdempotencyRecord)
        self.assertEqual(record.idempotency_key, "confirm:idem-1")
        self.assertEqual(record.status, "committed")
        self.assertEqual(record.response_payload, {"case_id": "CASE-1"})
        self.assertIn("from app.workbench_idempotency_records", executor.fetch_one_calls[0][0])

    def test_transaction_bound_reserve_sanitizes_payload_and_does_not_open_nested_transaction(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
            PostgresWorkbenchIdempotencyRepository,
        )

        connection = _RecordingSqlExecutor()
        transaction = _RecordingSqlExecutor(rows=[_record_row(status="reserved")])
        repository = PostgresWorkbenchIdempotencyRepository(connection).for_transaction(transaction)

        repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp:confirm:idem-1",
            request_payload={"case_id": "CASE-1", "password": "SECRET"},
        )

        self.assertFalse(connection.transaction_opened)
        self.assertEqual(len(transaction.fetch_one_calls), 1)
        sql, params = transaction.fetch_one_calls[0]
        self.assertIn("insert into app.workbench_idempotency_records", sql)
        stored_request_payload = _json_obj(params[6])
        self.assertNotIn("SECRET", repr(stored_request_payload))
        self.assertNotIn("password", stored_request_payload)

    def test_transaction_bound_reserve_reports_existing_reserved_without_nested_transaction(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
            PostgresWorkbenchIdempotencyRepository,
        )

        connection = _RecordingSqlExecutor()
        transaction = _RecordingSqlExecutor(rows=[_record_row(status="reserved", inserted=False)])
        repository = PostgresWorkbenchIdempotencyRepository(connection).for_transaction(transaction)

        reservation = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp:confirm:idem-1",
            request_payload={"case_id": "CASE-1"},
        )

        self.assertIsInstance(reservation, WorkbenchIdempotencyReservation)
        self.assertFalse(reservation.created)
        self.assertEqual(reservation.record.status, "reserved")
        self.assertFalse(connection.transaction_opened)
        sql, _params = transaction.fetch_one_calls[0]
        self.assertIn("on conflict", sql)
        self.assertIn("do nothing", sql)
        self.assertIn("for update", sql)

    def test_transaction_bound_reserve_reports_expired_reserved_takeover_without_nested_transaction(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
            PostgresWorkbenchIdempotencyRepository,
        )

        now = datetime(2026, 5, 31, 9, 0, tzinfo=timezone.utc)
        connection = _RecordingSqlExecutor()
        transaction = _RecordingSqlExecutor(
            rows=[
                _record_row(
                    status="reserved",
                    inserted=False,
                    reservation_outcome="taken_over_expired",
                    expires_at=now + timedelta(minutes=5),
                )
            ]
        )
        repository = PostgresWorkbenchIdempotencyRepository(connection).for_transaction(transaction)

        reservation = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp:confirm:idem-1",
            request_payload={"case_id": "CASE-RETRY", "authorization": "Bearer SECRET"},
            expires_at=now + timedelta(minutes=5),
        )

        self.assertIsInstance(reservation, WorkbenchIdempotencyReservation)
        self.assertFalse(reservation.created)
        self.assertTrue(reservation.taken_over_expired)
        self.assertFalse(connection.transaction_opened)
        sql, params = transaction.fetch_one_calls[0]
        self.assertIn("for update", sql)
        self.assertIn("expires_at <=", sql)
        self.assertIn("request_fingerprint", sql)
        stored_request_payload = _json_obj(params[6])
        self.assertNotIn("SECRET", repr(stored_request_payload))

    def test_transaction_bound_commit_updates_committed_record_with_sanitized_response(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
            PostgresWorkbenchIdempotencyRepository,
        )

        connection = _RecordingSqlExecutor()
        transaction = _RecordingSqlExecutor()
        repository = PostgresWorkbenchIdempotencyRepository(connection).for_transaction(transaction)

        repository.commit(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp:confirm:idem-1",
            response_payload={"case_id": "CASE-1", "token": "SECRET"},
            source_versions={"workbench:2026-05": 7},
            outbox_event_ids=["event-1"],
        )

        self.assertFalse(connection.transaction_opened)
        self.assertEqual(len(transaction.execute_calls), 1)
        sql, params = transaction.execute_calls[0]
        self.assertIn("update app.workbench_idempotency_records", sql)
        stored_response_payload = _json_obj(params[0])
        self.assertNotIn("SECRET", repr(stored_response_payload))
        self.assertNotIn("token", stored_response_payload)
        self.assertEqual(_json_obj(params[1]), {"workbench:2026-05": 7})
        self.assertEqual(_json_obj(params[2]), ["event-1"])

    def test_transaction_bound_mark_failed_updates_failed_record_with_sanitized_response(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
            PostgresWorkbenchIdempotencyRepository,
        )

        connection = _RecordingSqlExecutor()
        transaction = _RecordingSqlExecutor(
            rows=[
                _record_row(
                    status="failed",
                    response_payload={"error": "previous_failure"},
                    completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            ]
        )
        repository = PostgresWorkbenchIdempotencyRepository(connection).for_transaction(transaction)

        record = repository.mark_failed(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp:confirm:idem-1",
            response_payload={"error": "boom", "authorization": "Bearer SECRET"},
        )

        self.assertFalse(connection.transaction_opened)
        self.assertEqual(len(transaction.execute_calls), 1)
        sql, params = transaction.execute_calls[0]
        self.assertIn("update app.workbench_idempotency_records", sql)
        self.assertIn("status = 'failed'", sql)
        stored_response_payload = _json_obj(params[0])
        self.assertNotIn("SECRET", repr(stored_response_payload))
        self.assertNotIn("authorization", stored_response_payload)
        self.assertEqual(record.status, "failed")

    def test_server_uses_in_memory_idempotency_repository_by_default(self) -> None:
        app = object.__new__(Application)
        app._state_store = _PostgresStateStore(_RecordingSqlExecutor())
        app._runtime_repositories = SimpleNamespace(queue_repository=_QueueRepository())

        with patch.dict(os.environ, {"FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY": "0"}):
            uow = Application._workbench_confirm_link_unit_of_work(app)

        self.assertIsNotNone(uow)
        self.assertIsInstance(uow._idempotency_store, InMemoryWorkbenchIdempotencyRepository)

    def test_server_can_wire_durable_idempotency_repository_behind_explicit_flag(self) -> None:
        from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
            PostgresWorkbenchIdempotencyRepository,
        )

        app = object.__new__(Application)
        connection = _RecordingSqlExecutor()
        app._state_store = _PostgresStateStore(connection)
        app._runtime_repositories = SimpleNamespace(queue_repository=_QueueRepository())

        with patch.dict(os.environ, {"FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY": "1"}):
            uow = Application._workbench_confirm_link_unit_of_work(app)

        self.assertIsNotNone(uow)
        self.assertIsInstance(uow._idempotency_store, PostgresWorkbenchIdempotencyRepository)


if __name__ == "__main__":
    unittest.main()
