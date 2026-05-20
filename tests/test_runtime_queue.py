from __future__ import annotations

from datetime import datetime, timezone
import unittest

from fin_ops_platform.services.runtime_queue import RuntimeQueueDataError, RuntimeQueueRepository


class FakeTransaction:
    def __init__(self, rows: list[dict[str, object] | None] | None = None, counts: list[int] | None = None) -> None:
        self.rows = list(rows or [])
        self.counts = list(counts or [])
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []
        self.outcomes: list[str] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.calls.append(("fetch_one", sql, params))
        return self.rows.pop(0) if self.rows else None

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.calls.append(("fetch_all", sql, params))
        row = self.rows.pop(0) if self.rows else []
        return row if isinstance(row, list) else []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.calls.append(("execute", sql, params))
        return self.counts.pop(0) if self.counts else 0


class FakeConnection:
    def __init__(self, transaction: FakeTransaction) -> None:
        self.transaction_obj = transaction

    def transaction(self):
        transaction_obj = self.transaction_obj

        class TransactionContext:
            def __enter__(self) -> FakeTransaction:
                return transaction_obj

            def __exit__(self, exc_type, exc, traceback) -> bool:
                transaction_obj.outcomes.append("rollback" if exc_type is not None else "commit")
                return False

        return TransactionContext()


def event_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "event_id": "event-1",
        "tenant_id": "tenant-a",
        "event_type": "invoice.imported",
        "aggregate_type": "invoice",
        "aggregate_id": "invoice-1",
        "scope_type": "month",
        "scope_key": "2026-05",
        "dedupe_key": "invoice-1",
        "payload": {"invoice_id": "invoice-1"},
        "attempts": 0,
        "status": "pending",
    }
    row.update(overrides)
    return row


class RuntimeQueueRepositoryTests(unittest.TestCase):
    def test_enqueue_inserts_runtime_event_fields_and_returns_event(self) -> None:
        available_at = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        transaction = FakeTransaction(rows=[event_row()])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.enqueue(
            event_type="invoice.imported",
            aggregate_type="invoice",
            aggregate_id="invoice-1",
            scope_type="month",
            scope_key="2026-05",
            dedupe_key="invoice-1",
            payload={"invoice_id": "invoice-1"},
            tenant_id="tenant-a",
            available_at=available_at,
        )

        self.assertEqual(event.event_id, "event-1")
        self.assertEqual(event.payload, {"invoice_id": "invoice-1"})
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        for fragment in (
            "insert into job.outbox_events",
            "tenant_id",
            "event_type",
            "aggregate_type",
            "aggregate_id",
            "scope_type",
            "scope_key",
            "dedupe_key",
            "payload",
            "available_at",
            "returning",
        ):
            self.assertIn(fragment, normalized_sql)
        self.assertIn("on conflict", normalized_sql)
        self.assertEqual(params[:8], ("tenant-a", "invoice.imported", "invoice", "invoice-1", "month", "2026-05", "invoice-1", {"invoice_id": "invoice-1"}))
        self.assertEqual(params[8], available_at)

    def test_enqueue_dedupe_returns_existing_active_event_on_conflict(self) -> None:
        transaction = FakeTransaction(rows=[event_row(event_id="existing-event", attempts=2, status="processing")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.enqueue(event_type="invoice.imported", dedupe_key="invoice-1", payload={"ignored": True})

        self.assertEqual(event.event_id, "existing-event")
        self.assertEqual(event.status, "processing")
        _, sql, _ = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("on conflict", normalized_sql)
        self.assertIn("dedupe_key is not null", normalized_sql)
        self.assertIn("status in ('pending', 'processing')", normalized_sql)

    def test_claim_next_uses_skip_locked_timeout_and_event_type_filter(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="processing", attempts=1)])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.claim_next(
            worker_id="worker-1",
            event_types=["invoice.imported", "invoice.updated"],
            lock_timeout_seconds=120,
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.attempts, 1)
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("for update skip locked", normalized_sql)
        self.assertIn("locked_at < now() - (%s * interval '1 second')", normalized_sql)
        self.assertIn("event_type = any(%s)", normalized_sql)
        self.assertIn("attempts = attempts + 1", normalized_sql)
        self.assertIn("locked_by = %s", normalized_sql)
        self.assertEqual(params, ("worker-1", 120, ["invoice.imported", "invoice.updated"]))

    def test_claim_next_candidate_includes_stale_processing_events(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="processing", attempts=3)])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.claim_next(worker_id="new-worker", lock_timeout_seconds=300)

        self.assertIsNotNone(event)
        self.assertEqual(event.status, "processing")
        self.assertEqual(event.attempts, 3)
        _, sql, _ = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("(status = 'pending' and available_at <= now())", normalized_sql)
        self.assertRegex(
            normalized_sql,
            r"\(\s*status = 'processing' and available_at <= now\(\) and locked_at < now\(\) - \(%s \* interval '1 second'\)\s*\)",
        )
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("attempts = attempts + 1", normalized_sql)
        self.assertIn("for update skip locked", normalized_sql)

    def test_claim_next_raises_data_error_when_payload_is_not_object(self) -> None:
        transaction = FakeTransaction(rows=[event_row(payload=["not", "an", "object"])])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        with self.assertRaises(RuntimeQueueDataError) as context:
            repository.claim_next(worker_id="worker-1")

        message = str(context.exception)
        self.assertIn("event-1", message)
        self.assertIn("list", message)
        self.assertNotIn("not", message)
        self.assertEqual(transaction.outcomes, ["rollback"])

    def test_claim_next_raises_data_error_when_payload_is_empty_list(self) -> None:
        transaction = FakeTransaction(rows=[event_row(payload=[])])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        with self.assertRaises(RuntimeQueueDataError) as context:
            repository.claim_next(worker_id="worker-1")

        self.assertIn("event-1", str(context.exception))
        self.assertIn("list", str(context.exception))
        self.assertEqual(transaction.outcomes, ["rollback"])

    def test_claim_next_raises_data_error_when_payload_is_null(self) -> None:
        transaction = FakeTransaction(rows=[event_row(payload=None)])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        with self.assertRaises(RuntimeQueueDataError) as context:
            repository.claim_next(worker_id="worker-1")

        self.assertIn("event-1", str(context.exception))
        self.assertIn("NoneType", str(context.exception))
        self.assertEqual(transaction.outcomes, ["rollback"])

    def test_enqueue_defaults_missing_payload_key_to_empty_object(self) -> None:
        row = event_row()
        del row["payload"]
        transaction = FakeTransaction(rows=[row])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.enqueue(event_type="invoice.imported")

        self.assertEqual(event.payload, {})
        self.assertEqual(transaction.outcomes, ["commit"])

    def test_claim_next_without_event_type_filter_has_no_any_clause(self) -> None:
        transaction = FakeTransaction(rows=[None])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.claim_next(worker_id="worker-1")

        self.assertIsNone(event)
        _, sql, params = transaction.calls[0]
        self.assertNotIn("event_type = any", sql.lower())
        self.assertEqual(params, ("worker-1", 300))

    def test_complete_requires_processing_worker_lock_and_returns_bool(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="done")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        completed = repository.complete("event-1", "worker-1", result_payload={"ok": True})

        self.assertTrue(completed)
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("locked_by = %s", normalized_sql)
        self.assertIn("processed_at = now()", normalized_sql)
        self.assertIn("runtime_result", normalized_sql)
        self.assertEqual(params[0], {"ok": True})
        self.assertEqual(params[1:], ("event-1", "worker-1"))

    def test_complete_returns_false_when_worker_lock_does_not_match(self) -> None:
        transaction = FakeTransaction(rows=[None])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertFalse(repository.complete("event-1", "other-worker"))

    def test_fail_retry_and_permanent_require_processing_worker_lock_and_return_bool(self) -> None:
        retry_transaction = FakeTransaction(rows=[event_row(status="pending")])
        retry_repository = RuntimeQueueRepository(FakeConnection(retry_transaction))

        self.assertTrue(retry_repository.fail("event-1", "worker-1", "temporary", retry=True, retry_delay_seconds=30))

        _, retry_sql, retry_params = retry_transaction.calls[0]
        normalized_retry_sql = " ".join(retry_sql.lower().split())
        self.assertIn("status = 'pending'", normalized_retry_sql)
        self.assertIn("available_at = now() + (%s * interval '1 second')", normalized_retry_sql)
        self.assertIn("where id = %s", normalized_retry_sql)
        self.assertIn("status = 'processing'", normalized_retry_sql)
        self.assertIn("locked_by = %s", normalized_retry_sql)
        self.assertEqual(retry_params, ("temporary", 30, "event-1", "worker-1"))

        permanent_transaction = FakeTransaction(rows=[event_row(status="failed")])
        permanent_repository = RuntimeQueueRepository(FakeConnection(permanent_transaction))

        self.assertTrue(permanent_repository.fail("event-1", "worker-1", "fatal", retry=False))

        _, permanent_sql, permanent_params = permanent_transaction.calls[0]
        normalized_permanent_sql = " ".join(permanent_sql.lower().split())
        self.assertIn("status = 'failed'", normalized_permanent_sql)
        self.assertIn("processed_at = now()", normalized_permanent_sql)
        self.assertEqual(permanent_params, ("fatal", "event-1", "worker-1"))

    def test_backlog_summary_returns_counts_and_pending_age(self) -> None:
        transaction = FakeTransaction(
            rows=[
                [
                    {"status": "pending", "count": 2},
                    {"status": "processing", "count": 1},
                ],
                {"max_pending_age_seconds": 42.0},
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        summary = repository.backlog_summary()

        self.assertEqual(summary, {"counts_by_status": {"pending": 2, "processing": 1}, "max_pending_age_seconds": 42.0})
        self.assertEqual([call[0] for call in transaction.calls], ["fetch_all", "fetch_one"])
        self.assertIn("group by status", transaction.calls[0][1].lower())
        self.assertIn("extract(epoch from", transaction.calls[1][1].lower())


if __name__ == "__main__":
    unittest.main()
