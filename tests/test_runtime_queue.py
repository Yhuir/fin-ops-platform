from __future__ import annotations

from datetime import datetime, timezone
import unittest

from fin_ops_platform.services.runtime_queue import (
    DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES,
    RuntimeQueueDataError,
    RuntimeQueueEvent,
    RuntimeQueueRepository,
    RuntimeQueueSettings,
)


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
        self.transaction_open_count = 0

    def transaction(self):
        self.transaction_open_count += 1
        transaction_obj = self.transaction_obj

        class TransactionContext:
            def __enter__(self) -> FakeTransaction:
                return transaction_obj

            def __exit__(self, exc_type, exc, traceback) -> bool:
                transaction_obj.outcomes.append("rollback" if exc_type is not None else "commit")
                return False

        return TransactionContext()


class FailingTransactionConnection:
    def transaction(self):
        raise AssertionError("transaction-bound writer must use the supplied transaction")


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
        "schema_version": 1,
        "source_version": 123,
        "priority": "normal",
        "trace_id": "trace-1",
    }
    row.update(overrides)
    return row


class RuntimeQueueRepositoryTests(unittest.TestCase):
    def _enqueue_read_model_refresh_in_transaction(self, repository: RuntimeQueueRepository):
        method = getattr(repository, "enqueue_read_model_refresh_in_transaction", None)
        if not callable(method):
            self.fail("RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction is not implemented.")
        return method

    def test_settings_default_to_postgres_and_parse_reserved_rabbitmq_boundary(self) -> None:
        self.assertEqual(RuntimeQueueSettings.from_env({}).backend, "postgres")
        self.assertEqual(RuntimeQueueSettings.from_env({}).rabbitmq_dispatch_event_types, DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)
        self.assertIn("bank_detail.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)

        settings = RuntimeQueueSettings.from_env(
            {
                "FIN_OPS_QUEUE_BACKEND": "rabbitmq",
                "RABBITMQ_URL": "amqp://rabbitmq.internal",
                "RABBITMQ_VHOST": "/finops",
                "RABBITMQ_EXCHANGE": "finops.events",
                "RABBITMQ_QUEUE_PREFIX": "finops.runtime",
                "RABBITMQ_WORKBENCH_QUEUE": "finops.workbench.refresh",
                "RABBITMQ_WORKBENCH_ROUTING_KEY": "workbench.refresh",
                "RABBITMQ_DEAD_LETTER_EXCHANGE": "finops.events.dlx",
                "RABBITMQ_WORKBENCH_DEAD_LETTER_QUEUE": "finops.workbench.refresh.dlq",
                "RABBITMQ_PREFETCH": "25",
                "RABBITMQ_PUBLISH_CONFIRM": "false",
                "RABBITMQ_HEARTBEAT_SECONDS": "30",
                "RABBITMQ_BLOCKED_CONNECTION_TIMEOUT_SECONDS": "120",
                "RABBITMQ_MANAGEMENT_URL": "http://rabbitmq.internal:15672",
                "RABBITMQ_MANAGEMENT_USERNAME": "monitor",
                "RABBITMQ_MANAGEMENT_PASSWORD": "secret",
                "RABBITMQ_MANAGEMENT_TIMEOUT_SECONDS": "3",
                "RABBITMQ_SHADOW_PUBLISH": "true",
                "RABBITMQ_DISPATCH_EVENT_TYPES": "workbench.read_model.refresh,search.read_model.refresh",
            }
        )

        self.assertEqual(settings.backend, "rabbitmq")
        self.assertEqual(settings.rabbitmq_url, "amqp://rabbitmq.internal")
        self.assertEqual(settings.rabbitmq_vhost, "/finops")
        self.assertEqual(settings.rabbitmq_exchange, "finops.events")
        self.assertEqual(settings.rabbitmq_queue_prefix, "finops.runtime")
        self.assertEqual(settings.rabbitmq_workbench_queue, "finops.workbench.refresh")
        self.assertEqual(settings.rabbitmq_workbench_routing_key, "workbench.refresh")
        self.assertEqual(settings.rabbitmq_dead_letter_exchange, "finops.events.dlx")
        self.assertEqual(settings.rabbitmq_workbench_dead_letter_queue, "finops.workbench.refresh.dlq")
        self.assertEqual(settings.rabbitmq_prefetch, 25)
        self.assertFalse(settings.rabbitmq_publish_confirm)
        self.assertEqual(settings.rabbitmq_heartbeat_seconds, 30)
        self.assertEqual(settings.rabbitmq_blocked_connection_timeout_seconds, 120)
        self.assertEqual(settings.rabbitmq_management_url, "http://rabbitmq.internal:15672")
        self.assertEqual(settings.rabbitmq_management_username, "monitor")
        self.assertEqual(settings.rabbitmq_management_password, "secret")
        self.assertEqual(settings.rabbitmq_management_timeout_seconds, 3)
        self.assertTrue(settings.rabbitmq_shadow_publish)
        self.assertEqual(
            settings.rabbitmq_dispatch_event_types,
            ("workbench.read_model.refresh", "search.read_model.refresh"),
        )

    def test_event_envelope_contains_only_routing_identity_and_version(self) -> None:
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key="workbench.read_model.refresh:workbench:all",
            payload={"reason": "api_miss", "large_snapshot": {"must": "not be published"}},
            attempts=2,
            status="processing",
            schema_version=1,
            source_version=123,
            priority="normal",
            trace_id="trace-1",
        )

        self.assertEqual(
            event.to_envelope(),
            {
                "schema_version": 1,
                "event_id": "event-1",
                "event_type": "workbench.read_model.refresh",
                "scope_type": "workbench",
                "scope_key": "all",
                "source_version": 123,
                "priority": "normal",
                "trace_id": "trace-1",
            },
        )
        self.assertNotIn("payload", event.to_envelope())
        self.assertEqual(event.attempt_count, 2)

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
        self.assertIn("status = 'pending'", normalized_sql)

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

    def test_claim_events_is_batch_interface_over_postgres_claims(self) -> None:
        transaction = FakeTransaction(
            rows=[
                event_row(event_id="event-1", status="processing", attempts=1),
                event_row(event_id="event-2", status="processing", attempts=1),
                None,
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        events = repository.claim_events(
            worker_id="worker-1",
            event_types=["invoice.imported"],
            lock_timeout_seconds=120,
            limit=3,
        )

        self.assertEqual([event.event_id for event in events], ["event-1", "event-2"])
        self.assertEqual(len(transaction.calls), 3)

    def test_claim_event_by_id_locks_specific_pending_event(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="processing", attempts=1)])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.claim_event_by_id(
            event_id="event-1",
            worker_id="worker-1",
            event_types=["invoice.imported"],
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.event_id, "event-1")
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("where id = %s", normalized_sql)
        self.assertIn("status = 'pending'", normalized_sql)
        self.assertIn("available_at <= now()", normalized_sql)
        self.assertIn("event_type = any(%s)", normalized_sql)
        self.assertEqual(params, ("worker-1", "event-1", 300, ["invoice.imported"]))

    def test_claim_event_by_id_can_reclaim_stale_processing_event(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="processing", attempts=2)])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.claim_event_by_id(
            event_id="event-1",
            worker_id="worker-1",
            event_types=["invoice.imported"],
            lock_timeout_seconds=180,
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.event_id, "event-1")
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("where id = %s", normalized_sql)
        self.assertIn("(status = 'pending' and available_at <= now())", normalized_sql)
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("locked_at < now() - (%s * interval '1 second')", normalized_sql)
        self.assertIn("event_type = any(%s)", normalized_sql)
        self.assertEqual(params, ("worker-1", "event-1", 180, ["invoice.imported"]))

    def test_claim_publishable_events_uses_publish_status_and_skip_locked(self) -> None:
        transaction = FakeTransaction(rows=[[event_row(status="pending", publish_status="publishing", publish_attempt_count=2)]])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        events = repository.claim_publishable_events(
            publisher_id="publisher-1",
            event_types=["workbench.read_model.refresh"],
            lock_timeout_seconds=120,
            limit=10,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].publish_status, "publishing")
        self.assertEqual(events[0].publish_attempt_count, 2)
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("publish_status = 'publishing'", normalized_sql)
        self.assertIn("publish_attempt_count = publish_attempt_count + 1", normalized_sql)
        self.assertIn("publish_status in ('unpublished', 'failed')", normalized_sql)
        self.assertIn("for update skip locked", normalized_sql)
        self.assertEqual(params, ("publisher-1", 120, ["workbench.read_model.refresh"], 10))

    def test_mark_published_requires_publish_lock_and_records_confirm(self) -> None:
        transaction = FakeTransaction(rows=[{"id": "event-1"}])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.mark_published(
                "event-1",
                publisher_id="publisher-1",
                exchange="finops.events",
                routing_key="workbench.read_model.refresh",
                message_id="event-1",
                confirm_latency_ms=12.3456,
            )
        )

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("publish_status = 'published'", normalized_sql)
        self.assertIn("publish_confirmed_at = now()", normalized_sql)
        self.assertIn("publish_status = 'publishing'", normalized_sql)
        self.assertIn("publish_locked_by = %s", normalized_sql)
        self.assertEqual(params[0:3], ("finops.events", "workbench.read_model.refresh", "event-1"))
        self.assertEqual(params[-2:], ("event-1", "publisher-1"))

    def test_mark_publish_failed_schedules_publish_retry(self) -> None:
        transaction = FakeTransaction(rows=[{"id": "event-1"}])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.mark_publish_failed(
                "event-1",
                publisher_id="publisher-1",
                error="broker down",
                retry_delay_seconds=45,
            )
        )

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("publish_status = 'failed'", normalized_sql)
        self.assertIn("next_publish_at = now() + (%s * interval '1 second')", normalized_sql)
        self.assertIn("jsonb_build_object('error', %s::text, 'retry_delay_seconds', %s::integer)", normalized_sql)
        self.assertEqual(params, ("broker down", 45, "broker down", 45, "event-1", "publisher-1"))

    def test_reset_publish_state_marks_pending_event_unpublished(self) -> None:
        transaction = FakeTransaction(rows=[{"id": "event-1"}])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(repository.reset_publish_state("event-1", reason="operator"))

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("publish_status = 'unpublished'", normalized_sql)
        self.assertIn("rabbitmq_republish", normalized_sql)
        self.assertIn("status = 'pending'", normalized_sql)
        self.assertEqual(params, ("operator", "event-1"))

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

    def test_enqueue_read_model_refresh_increments_and_returns_source_version(self) -> None:
        transaction = FakeTransaction(
            rows=[
                {"source_version": 3},
                event_row(
                    event_type="workbench.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="2026-05",
                    scope_type="workbench",
                    scope_key="2026-05",
                    dedupe_key="workbench.read_model.refresh:workbench:2026-05",
                    payload={"scope_type": "workbench", "scope_key": "2026-05", "reason": "test", "source_version": 3},
                    source_version=3,
                    priority="high",
                    trace_id="trace-read-model",
                ),
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.enqueue_read_model_refresh(
            scope_type="workbench",
            scope_key="2026-05",
            reason="test",
            priority="high",
            trace_id="trace-read-model",
        )

        self.assertEqual(event.payload["source_version"], 3)
        self.assertEqual(event.source_version, 3)
        self.assertEqual(event.priority, "high")
        self.assertEqual(event.trace_id, "trace-read-model")
        self.assertEqual(len(transaction.calls), 2)
        _, dirty_sql, _ = transaction.calls[0]
        _, outbox_sql, outbox_params = transaction.calls[1]
        normalized_dirty_sql = " ".join(dirty_sql.lower().split())
        self.assertIn("select max(existing.source_version) + 1", normalized_dirty_sql)
        self.assertIn("source_version = job.read_model_dirty_scopes.source_version + 1", " ".join(dirty_sql.lower().split()))
        normalized_outbox_sql = " ".join(outbox_sql.lower().split())
        self.assertIn("source_version", normalized_outbox_sql)
        self.assertIn("priority", normalized_outbox_sql)
        self.assertIn("trace_id", normalized_outbox_sql)
        self.assertIn("schema_version", normalized_outbox_sql)
        self.assertIn("status = 'pending'", normalized_outbox_sql)
        self.assertIn("payload = job.outbox_events.payload || excluded.payload", normalized_outbox_sql)
        self.assertEqual(
            outbox_params[6:10],
            (3, "high", "trace-read-model", {"scope_type": "workbench", "scope_key": "2026-05", "reason": "test", "source_version": 3}),
        )

    def test_enqueue_read_model_refresh_in_transaction_uses_supplied_transaction_without_opening_connection_context(self) -> None:
        transaction = FakeTransaction(
            rows=[
                {"source_version": 5},
                event_row(
                    event_type="workbench.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="2026-05",
                    scope_type="workbench",
                    scope_key="2026-05",
                    dedupe_key="workbench.read_model.refresh:workbench:2026-05",
                    payload={"scope_type": "workbench", "scope_key": "2026-05", "reason": "confirm_link", "source_version": 5},
                    source_version=5,
                ),
            ]
        )
        repository = RuntimeQueueRepository(FailingTransactionConnection())  # type: ignore[arg-type]
        enqueue_in_transaction = self._enqueue_read_model_refresh_in_transaction(repository)

        event = enqueue_in_transaction(
            transaction=transaction,
            scope_type="workbench",
            scope_key="2026-05",
            reason="confirm_link",
        )

        self.assertEqual(event.source_version, 5)
        self.assertEqual(len(transaction.calls), 2)

    def test_enqueue_read_model_refresh_in_transaction_preserves_source_version_payload_and_outbox_contract(self) -> None:
        transaction = FakeTransaction(
            rows=[
                {"source_version": 8},
                event_row(
                    event_type="workbench.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="2026-05",
                    scope_type="workbench",
                    scope_key="2026-05",
                    dedupe_key="workbench.read_model.refresh:workbench:2026-05",
                    payload={"scope_type": "workbench", "scope_key": "2026-05", "reason": "exception_apply", "source_version": 8},
                    source_version=8,
                    priority="high",
                    trace_id="trace-read-model",
                ),
            ]
        )
        repository = RuntimeQueueRepository(FailingTransactionConnection())  # type: ignore[arg-type]
        enqueue_in_transaction = self._enqueue_read_model_refresh_in_transaction(repository)

        event = enqueue_in_transaction(
            transaction=transaction,
            scope_type="workbench",
            scope_key="2026-05",
            reason="exception_apply",
            priority="high",
            trace_id="trace-read-model",
        )

        self.assertEqual(event.payload["source_version"], 8)
        self.assertEqual(event.source_version, 8)
        self.assertEqual(event.priority, "high")
        self.assertEqual(event.trace_id, "trace-read-model")
        _, dirty_sql, dirty_params = transaction.calls[0]
        _, outbox_sql, outbox_params = transaction.calls[1]
        normalized_dirty_sql = " ".join(dirty_sql.lower().split())
        normalized_outbox_sql = " ".join(outbox_sql.lower().split())
        self.assertIn("insert into job.read_model_dirty_scopes", normalized_dirty_sql)
        self.assertIn("source_version = job.read_model_dirty_scopes.source_version + 1", normalized_dirty_sql)
        self.assertIn("insert into job.outbox_events", normalized_outbox_sql)
        self.assertIn("payload = job.outbox_events.payload || excluded.payload", normalized_outbox_sql)
        self.assertEqual(
            dirty_params,
            (
                "default",
                "workbench",
                "2026-05",
                "exception_apply",
                {"scope_type": "workbench", "scope_key": "2026-05", "reason": "exception_apply"},
                {"scope_type": "workbench", "scope_key": "2026-05", "reason": "exception_apply"},
                "default",
                "workbench",
                "2026-05",
                "high",
                "trace-read-model",
            ),
        )
        self.assertEqual(
            outbox_params,
            (
                "default",
                "workbench.read_model.refresh",
                "2026-05",
                "workbench",
                "2026-05",
                "workbench.read_model.refresh:workbench:2026-05",
                8,
                "high",
                "trace-read-model",
                {"scope_type": "workbench", "scope_key": "2026-05", "reason": "exception_apply", "source_version": 8},
                {"scope_type": "workbench", "scope_key": "2026-05", "reason": "exception_apply", "source_version": 8},
            ),
        )

    def test_enqueue_read_model_refresh_delegates_to_transaction_bound_writer(self) -> None:
        transaction = FakeTransaction(
            rows=[
                {"source_version": 6},
                event_row(
                    event_type="workbench.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="2026-05",
                    scope_type="workbench",
                    scope_key="2026-05",
                    dedupe_key="workbench.read_model.refresh:workbench:2026-05",
                    payload={"scope_type": "workbench", "scope_key": "2026-05", "reason": "test", "source_version": 6},
                    source_version=6,
                ),
            ]
        )
        connection = FakeConnection(transaction)
        repository = RuntimeQueueRepository(connection)
        delegated_transactions: list[FakeTransaction] = []
        original = self._enqueue_read_model_refresh_in_transaction(repository)

        def recording_delegate(**kwargs):
            delegated_transactions.append(kwargs["transaction"])
            return original(**kwargs)

        repository.enqueue_read_model_refresh_in_transaction = recording_delegate  # type: ignore[method-assign]

        event = repository.enqueue_read_model_refresh(scope_type="workbench", scope_key="2026-05", reason="test")

        self.assertEqual(event.source_version, 6)
        self.assertEqual(connection.transaction_open_count, 1)
        self.assertEqual(delegated_transactions, [transaction])
        self.assertEqual(transaction.outcomes, ["commit"])

    def test_enqueue_read_model_refresh_initializes_new_scope_from_historical_source_version(self) -> None:
        transaction = FakeTransaction(
            rows=[
                {"source_version": 4},
                event_row(
                    event_type="workbench.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="2026-05",
                    scope_type="workbench",
                    scope_key="2026-05",
                    dedupe_key="workbench.read_model.refresh:workbench:2026-05",
                    payload={"scope_type": "workbench", "scope_key": "2026-05", "reason": "test", "source_version": 4},
                ),
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.enqueue_read_model_refresh(scope_type="workbench", scope_key="2026-05", reason="test")

        self.assertEqual(event.payload["source_version"], 4)
        _, dirty_sql, dirty_params = transaction.calls[0]
        normalized_sql = " ".join(dirty_sql.lower().split())
        self.assertIn("select max(existing.source_version) + 1", normalized_sql)
        self.assertEqual(
            dirty_params,
            (
                "default",
                "workbench",
                "2026-05",
                "test",
                {"scope_type": "workbench", "scope_key": "2026-05", "reason": "test"},
                {"scope_type": "workbench", "scope_key": "2026-05", "reason": "test"},
                "default",
                "workbench",
                "2026-05",
                "normal",
                None,
            ),
        )

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

    def test_complete_read_model_refresh_is_source_version_guarded(self) -> None:
        transaction = FakeTransaction(rows=[{"id": "dirty-1"}])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.complete_read_model_refresh(
                tenant_id="default",
                scope_type="workbench",
                scope_key="2026-05",
                source_version=7,
            )
        )

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("source_version <= %s", normalized_sql)
        self.assertEqual(params, ("default", "workbench", "2026-05", 7))

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
        self.assertEqual(retry_params, ("temporary", 30, 30, "event-1", "worker-1"))

        permanent_transaction = FakeTransaction(rows=[event_row(status="failed")])
        permanent_repository = RuntimeQueueRepository(FakeConnection(permanent_transaction))

        self.assertTrue(permanent_repository.fail("event-1", "worker-1", "fatal", retry=False))

        _, permanent_sql, permanent_params = permanent_transaction.calls[0]
        normalized_permanent_sql = " ".join(permanent_sql.lower().split())
        self.assertIn("status = 'failed'", normalized_permanent_sql)
        self.assertIn("processed_at = now()", normalized_permanent_sql)
        self.assertEqual(permanent_params, ("fatal", "event-1", "worker-1"))

    def test_fail_event_dead_letters_after_max_attempts_and_preserves_trace(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="dead_lettered")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.fail_event(
                "event-1",
                "worker-1",
                "temporary",
                retryable=True,
                retry_delay_seconds=30,
                max_attempts=3,
            )
        )

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("then 'dead_lettered' else 'pending' end", normalized_sql)
        self.assertIn("dead_lettered_at", normalized_sql)
        self.assertIn("runtime_failure", normalized_sql)
        self.assertIn("jsonb_build_object('error', %s::text, 'retryable', true, 'max_attempts', %s::integer)", normalized_sql)
        self.assertEqual(params[-2:], ("event-1", "worker-1"))
        self.assertEqual(params[0], 3)
        self.assertEqual(params[1], "temporary")
        self.assertEqual(params[3], 30)

    def test_requeue_event_restores_failed_or_dead_lettered_event_to_pending(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="pending")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(repository.requeue_event("event-1", reason="operator_repair"))

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status = 'pending'", normalized_sql)
        self.assertIn("where id = %s", normalized_sql)
        self.assertIn("status in ('failed', 'dead_lettered', 'pending')", normalized_sql)
        self.assertIn("manual_requeue", normalized_sql)
        self.assertIn("publish_status = 'unpublished'", normalized_sql)
        self.assertIn("jsonb_build_object('reason', %s::text, 'requeued_at', now())", normalized_sql)
        self.assertEqual(params, ("operator_repair", "event-1"))

    def test_release_event_restores_worker_locked_processing_event_to_pending(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="pending")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(repository.release_event("event-1", "worker-1", reason="shutdown_signal_15"))

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status = 'pending'", normalized_sql)
        self.assertIn("available_at = now()", normalized_sql)
        self.assertIn("locked_by = null", normalized_sql)
        self.assertIn("locked_at = null", normalized_sql)
        self.assertIn("attempts = greatest(coalesce(attempts, 0) - 1, 0)", normalized_sql)
        self.assertIn("runtime_shutdown_release", normalized_sql)
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("locked_by = %s", normalized_sql)
        self.assertEqual(params, ("shutdown_signal_15", "event-1", "worker-1"))

    def test_resolve_dead_letter_event_marks_done_with_operator_resolution(self) -> None:
        transaction = FakeTransaction(rows=[{"id": "event-1"}])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(repository.resolve_dead_letter_event("event-1", reason="readiness_converged"))

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status = 'done'", normalized_sql)
        self.assertIn("processed_at = coalesce(processed_at, now())", normalized_sql)
        self.assertIn("operator_resolution", normalized_sql)
        self.assertIn("where id = %s", normalized_sql)
        self.assertIn("status = 'dead_lettered'", normalized_sql)
        self.assertEqual(params, ("readiness_converged", "event-1"))

    def test_retry_is_explicit_alias_for_retryable_failure(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="pending")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(repository.retry("event-1", "worker-1", "temporary", retry_delay_seconds=45))

        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status = 'pending'", normalized_sql)
        self.assertIn("available_at = now() + (%s * interval '1 second')", normalized_sql)
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("locked_by = %s", normalized_sql)
        self.assertEqual(params, ("temporary", 45, 45, "event-1", "worker-1"))

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
