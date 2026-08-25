from __future__ import annotations

import unittest
from datetime import datetime, timezone

from fin_ops_platform.services.postgres_connection import PostgresTransaction
from fin_ops_platform.services.runtime_queue import (
    RuntimeQueueDataError,
    RuntimeQueueEvent,
    RuntimeQueueRepository,
    RuntimeQueueSettings,
)
from psycopg.types.json import Jsonb


class FakeTransaction:
    def __init__(self, rows: list[dict[str, object] | Exception | None] | None = None, counts: list[int] | None = None) -> None:
        self.rows = list(rows or [])
        self.counts = list(counts or [])
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []
        self.outcomes: list[str] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.calls.append(("fetch_one", sql, params))
        row = self.rows.pop(0) if self.rows else None
        if isinstance(row, Exception):
            raise row
        return row

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
    def test_settings_default_to_postgres_and_reject_other_backends(self) -> None:
        self.assertEqual(RuntimeQueueSettings.from_env({}).backend, "postgres")
        self.assertEqual(RuntimeQueueSettings.from_env({}).summary(), {"queue_backend": "postgres"})
        with self.assertRaisesRegex(RuntimeQueueDataError, "must be postgres"):
            RuntimeQueueSettings.from_env({"FIN_OPS_QUEUE_BACKEND": "rabbitmq"})

    def test_event_envelope_contains_only_routing_identity_and_version(self) -> None:
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="oa.sync",
            aggregate_type="oa",
            aggregate_id="all",
            scope_type="oa",
            scope_key="all",
            dedupe_key="oa.sync:oa:all",
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
                "event_type": "oa.sync",
                "scope_type": "oa",
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

    def test_claim_next_can_filter_scope_keys_for_split_worker_lanes(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="processing", attempts=1, scope_key="all")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.claim_next(
            worker_id="worker-1",
            event_types=["workbench_relation.read_model.refresh"],
            lock_timeout_seconds=120,
            scope_keys=["all"],
            exclude_scope_keys=["2026-02"],
        )

        self.assertIsNotNone(event)
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("scope_key = any(%s)", normalized_sql)
        self.assertIn("not (scope_key = any(%s))", normalized_sql)
        self.assertEqual(params, ("worker-1", 120, ["workbench_relation.read_model.refresh"], ["all"], ["2026-02"]))

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

    def test_claim_event_by_id_honors_scope_filters(self) -> None:
        transaction = FakeTransaction(rows=[event_row(status="processing", attempts=1, scope_key="all")])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.claim_event_by_id(
            event_id="event-1",
            worker_id="worker-1",
            event_types=["workbench_relation.read_model.refresh"],
            scope_keys=["all"],
        )

        self.assertIsNotNone(event)
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("scope_key = any(%s)", normalized_sql)
        self.assertEqual(params, ("worker-1", "event-1", 300, ["workbench_relation.read_model.refresh"], ["all"]))

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

    def test_get_event_status_reads_durable_result_without_mutation(self) -> None:
        transaction = FakeTransaction(
            rows=[
                {
                    "event_id": "event-1",
                    "event_type": "oa.sync",
                    "status": "done",
                    "payload": {"operation": "refresh_attachments"},
                    "last_error": None,
                    "runtime_result": {"rows": []},
                }
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        result = repository.get_event_status("event-1")

        self.assertEqual(result["runtime_result"], {"rows": []})
        _, sql, params = transaction.calls[0]
        self.assertIn("raw_payload -> 'runtime_result'", sql)
        self.assertEqual(params, ("event-1",))

    def test_get_active_event_by_dedupe_key_reads_pending_or_processing_event(self) -> None:
        transaction = FakeTransaction(
            rows=[
                event_row(
                    event_id="active-event",
                    event_type="oa.sync",
                    status="processing",
                    dedupe_key="oa.sync:refresh_attachments:identity",
                )
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        event = repository.get_active_event_by_dedupe_key(
            "oa.sync:refresh_attachments:identity",
            tenant_id="tenant-a",
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_id, "active-event")
        self.assertEqual(event.status, "processing")
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status in ('pending', 'processing')", normalized_sql)
        self.assertIn("order by created_at desc", normalized_sql)
        self.assertEqual(
            params,
            ("tenant-a", "oa.sync:refresh_attachments:identity"),
        )

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
        self.assertIn("attempts = 0", normalized_sql)
        self.assertNotIn("attempt_count =", normalized_sql)
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

    def test_release_stale_processing_events_requeues_with_operator_audit(self) -> None:
        transaction = FakeTransaction(rows=[[event_row(status="pending")]])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        rows = repository.release_stale_processing_events(
            stale_after_seconds=300,
            limit=25,
            reason="stale_processing_repair",
            event_types=["workbench_relation.read_model.refresh"],
        )

        self.assertEqual(len(rows), 1)
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("locked_at < now() - (%s * interval '1 second')", normalized_sql)
        self.assertIn("stale.event_type = any(%s)", normalized_sql)
        self.assertIn("row_number() over", normalized_sql)
        self.assertIn("dedupe_rank = 1", normalized_sql)
        self.assertIn("pending.status = 'pending'", normalized_sql)
        self.assertIn("for update skip locked", normalized_sql)
        self.assertIn("status = 'pending'", normalized_sql)
        self.assertIn("attempts = greatest(coalesce(event.attempts, 0) - 1, 0)", normalized_sql)
        self.assertIn("operator_stale_processing_release", normalized_sql)
        self.assertIn("previous_locked_by", normalized_sql)
        self.assertIn("previous_locked_at", normalized_sql)
        self.assertEqual(
            params,
            (
                300,
                ["workbench_relation.read_model.refresh"],
                25,
                "stale_processing_repair",
                300,
            ),
        )

    def test_resolve_superseded_processing_events_marks_obsolete_processing_done(self) -> None:
        transaction = FakeTransaction(rows=[[event_row(status="done")]])
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        rows = repository.resolve_superseded_processing_events(
            stale_after_seconds=300,
            limit=25,
            reason="stale_processing_superseded",
            event_types=["workbench_relation.read_model.refresh"],
        )

        self.assertEqual(len(rows), 1)
        _, sql, params = transaction.calls[0]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("join lateral", normalized_sql)
        self.assertIn("newer.status in ('pending', 'processing', 'done')", normalized_sql)
        self.assertIn("coalesce(newer.source_version, 0) >= coalesce(stale.source_version, 0)", normalized_sql)
        self.assertIn("stale.event_type = any(%s)", normalized_sql)
        self.assertIn("status = 'done'", normalized_sql)
        self.assertIn("operator_superseded_processing_resolution", normalized_sql)
        self.assertIn("covered_by_event_id", normalized_sql)
        self.assertEqual(
            params,
            (
                300,
                ["workbench_relation.read_model.refresh"],
                25,
                "stale_processing_superseded",
                300,
            ),
        )

    def test_defer_event_delays_dependency_retry_without_failure_or_dead_letter(self) -> None:
        locked_at = datetime(2026, 6, 14, 5, 6, tzinfo=timezone.utc)
        created_at = datetime(2026, 6, 14, 5, 5, tzinfo=timezone.utc)
        transaction = FakeTransaction(
            rows=[
                {
                    "event_id": "event-1",
                    "tenant_id": "tenant-a",
                    "dedupe_key": "workbench_relation.read_model.refresh:workbench_relation:2026-02",
                    "source_version": 197,
                    "locked_by": "worker-1",
                    "locked_at": locked_at,
                    "created_at": created_at,
                },
                None,
                {"event_id": "event-1"},
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.defer_event(
                "event-1",
                "worker-1",
                reason="workbench_relation_read_model_not_fresh",
                delay_seconds=0.25,
            )
        )

        self.assertEqual(len(transaction.calls), 3)
        _, lock_sql, lock_params = transaction.calls[0]
        _, cover_sql, cover_params = transaction.calls[1]
        _, defer_sql, defer_params = transaction.calls[2]
        normalized_lock_sql = " ".join(lock_sql.lower().split())
        normalized_cover_sql = " ".join(cover_sql.lower().split())
        normalized_sql = " ".join(defer_sql.lower().split())
        self.assertIn("status = 'processing'", normalized_lock_sql)
        self.assertIn("locked_by = %s", normalized_lock_sql)
        self.assertIn("for update", normalized_lock_sql)
        self.assertIn("status in ('pending', 'processing', 'done')", normalized_cover_sql)
        self.assertIn("coalesce(source_version, 0) >= coalesce(%s, 0)", normalized_cover_sql)
        self.assertIn("created_at > %s", normalized_cover_sql)
        self.assertIn("created_at = %s and id > %s::uuid", normalized_cover_sql)
        self.assertIn("order by coalesce(source_version, 0) desc", normalized_cover_sql)
        self.assertIn("status = 'pending'", normalized_sql)
        self.assertIn("available_at = now() + (%s::double precision * interval '1 second')", normalized_sql)
        self.assertIn("attempts = greatest(coalesce(attempts, 0) - 1, 0)", normalized_sql)
        self.assertIn("runtime_defer", normalized_sql)
        self.assertIn("'delay_seconds', %s::double precision", normalized_sql)
        self.assertIn("status = 'processing'", normalized_sql)
        self.assertIn("locked_by = %s", normalized_sql)
        self.assertIn("not exists", normalized_sql)
        self.assertNotIn("dead_lettered", normalized_sql)
        self.assertEqual(lock_params, ("event-1", "worker-1"))
        self.assertEqual(
            cover_params,
            (
                "tenant-a",
                "workbench_relation.read_model.refresh:workbench_relation:2026-02",
                "event-1",
                197,
                created_at,
                created_at,
                "event-1",
            ),
        )
        self.assertEqual(
            defer_params,
            (
                0.25,
                "workbench_relation_read_model_not_fresh",
                0.25,
                "event-1",
                "worker-1",
            ),
        )

    def test_defer_event_does_not_let_older_done_event_cover_newer_processing_event(self) -> None:
        locked_at = datetime(2026, 6, 20, 15, 35, tzinfo=timezone.utc)
        created_at = datetime(2026, 6, 20, 15, 34, tzinfo=timezone.utc)
        transaction = FakeTransaction(
            rows=[
                {
                    "event_id": "event-1",
                    "tenant_id": "tenant-a",
                    "dedupe_key": "workbench_relation.read_model.refresh:workbench_relation:2026-03",
                    "source_version": 2,
                    "locked_by": "worker-1",
                    "locked_at": locked_at,
                    "created_at": created_at,
                },
                None,
                {"event_id": "event-1"},
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.defer_event(
                "event-1",
                "worker-1",
                reason="workbench_relation_read_model_not_fresh",
                delay_seconds=0.25,
            )
        )

        self.assertEqual(len(transaction.calls), 3)
        _, cover_sql, cover_params = transaction.calls[1]
        _, defer_sql, _ = transaction.calls[2]
        normalized_cover_sql = " ".join(cover_sql.lower().split())
        normalized_defer_sql = " ".join(defer_sql.lower().split())
        self.assertIn("coalesce(source_version, 0) >= coalesce(%s, 0)", normalized_cover_sql)
        self.assertIn("created_at > %s", normalized_cover_sql)
        self.assertIn("created_at = %s and id > %s::uuid", normalized_cover_sql)
        self.assertIn("status = 'pending'", normalized_defer_sql)
        self.assertIn("runtime_defer", normalized_defer_sql)
        self.assertNotIn("runtime_defer_superseded", normalized_defer_sql)
        self.assertEqual(
            cover_params,
            (
                "tenant-a",
                "workbench_relation.read_model.refresh:workbench_relation:2026-03",
                "event-1",
                2,
                created_at,
                created_at,
                "event-1",
            ),
        )

    def test_defer_event_resolves_current_processing_when_pending_same_dedupe_exists(self) -> None:
        locked_at = datetime(2026, 6, 14, 5, 6, tzinfo=timezone.utc)
        created_at = datetime(2026, 6, 14, 5, 5, tzinfo=timezone.utc)
        transaction = FakeTransaction(
            rows=[
                {
                    "event_id": "event-1",
                    "tenant_id": "tenant-a",
                    "dedupe_key": "workbench_relation.read_model.refresh:workbench_relation:2026-02",
                    "source_version": 197,
                    "locked_by": "worker-1",
                    "locked_at": locked_at,
                    "created_at": created_at,
                },
                {
                    "event_id": "event-2",
                    "status": "pending",
                    "source_version": 198,
                },
                {"event_id": "event-1"},
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.defer_event(
                "event-1",
                "worker-1",
                reason="workbench_relation_read_model_not_fresh",
                delay_seconds=3,
            )
        )

        self.assertEqual(len(transaction.calls), 3)
        _, lock_sql, lock_params = transaction.calls[0]
        _, cover_sql, cover_params = transaction.calls[1]
        _, resolve_sql, resolve_params = transaction.calls[2]
        normalized_lock_sql = " ".join(lock_sql.lower().split())
        normalized_cover_sql = " ".join(cover_sql.lower().split())
        normalized_resolve_sql = " ".join(resolve_sql.lower().split())
        self.assertIn("status = 'processing'", normalized_lock_sql)
        self.assertIn("for update", normalized_lock_sql)
        self.assertIn("status in ('pending', 'processing', 'done')", normalized_cover_sql)
        self.assertIn("coalesce(source_version, 0) >= coalesce(%s, 0)", normalized_cover_sql)
        self.assertIn("created_at > %s", normalized_cover_sql)
        self.assertIn("created_at = %s and id > %s::uuid", normalized_cover_sql)
        self.assertIn("status = 'done'", normalized_resolve_sql)
        self.assertIn("runtime_defer_superseded", normalized_resolve_sql)
        self.assertIn("covered_by_event_id", normalized_resolve_sql)
        self.assertNotIn("status = 'pending'", normalized_resolve_sql)
        self.assertEqual(lock_params, ("event-1", "worker-1"))
        self.assertEqual(
            cover_params,
            (
                "tenant-a",
                "workbench_relation.read_model.refresh:workbench_relation:2026-02",
                "event-1",
                197,
                created_at,
                created_at,
                "event-1",
            ),
        )
        self.assertEqual(
            resolve_params,
            (
                "workbench_relation_read_model_not_fresh",
                3.0,
                "worker-1",
                locked_at,
                "event-2",
                "pending",
                198,
                "event-1",
                "worker-1",
            ),
        )

    def test_defer_event_resolves_unique_collision_from_concurrent_pending_cover(self) -> None:
        class UniqueViolation(RuntimeError):
            sqlstate = "23505"

        locked_at = datetime(2026, 6, 14, 5, 26, tzinfo=timezone.utc)
        created_at = datetime(2026, 6, 14, 5, 25, tzinfo=timezone.utc)
        target = {
            "event_id": "event-1",
            "tenant_id": "tenant-a",
            "dedupe_key": "workbench_relation.read_model.refresh:bank_detail:2026-02",
            "source_version": 13357,
            "locked_by": "worker-1",
            "locked_at": locked_at,
            "created_at": created_at,
        }
        transaction = FakeTransaction(
            rows=[
                target,
                None,
                UniqueViolation("duplicate key value violates unique constraint"),
                target,
                {
                    "event_id": "event-2",
                    "status": "pending",
                    "source_version": 13358,
                },
                {"event_id": "event-1"},
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        self.assertTrue(
            repository.defer_event(
                "event-1",
                "worker-1",
                reason="workbench_relation_read_model_not_fresh",
                delay_seconds=0.25,
            )
        )

        self.assertEqual(transaction.outcomes, ["rollback", "commit"])
        self.assertEqual(len(transaction.calls), 6)
        _, first_cover_sql, first_cover_params = transaction.calls[1]
        _, pending_update_sql, _ = transaction.calls[2]
        _, second_cover_sql, second_cover_params = transaction.calls[4]
        _, resolve_sql, resolve_params = transaction.calls[5]
        normalized_first_cover_sql = " ".join(first_cover_sql.lower().split())
        normalized_second_cover_sql = " ".join(second_cover_sql.lower().split())
        normalized_pending_update_sql = " ".join(pending_update_sql.lower().split())
        normalized_resolve_sql = " ".join(resolve_sql.lower().split())
        self.assertIn("status in ('pending', 'processing', 'done')", normalized_first_cover_sql)
        self.assertIn("coalesce(source_version, 0) >= coalesce(%s, 0)", normalized_first_cover_sql)
        self.assertIn("created_at > %s", normalized_first_cover_sql)
        self.assertIn("created_at = %s and id > %s::uuid", normalized_first_cover_sql)
        self.assertIn("status = 'pending'", normalized_pending_update_sql)
        self.assertIn("status in ('pending', 'processing', 'done')", normalized_second_cover_sql)
        self.assertIn("created_at > %s", normalized_second_cover_sql)
        self.assertIn("created_at = %s and id > %s::uuid", normalized_second_cover_sql)
        self.assertIn("status = 'done'", normalized_resolve_sql)
        self.assertIn("'collision', true", normalized_resolve_sql)
        self.assertEqual(
            first_cover_params,
            (
                "tenant-a",
                "workbench_relation.read_model.refresh:bank_detail:2026-02",
                "event-1",
                13357,
                created_at,
                created_at,
                "event-1",
            ),
        )
        self.assertEqual(
            second_cover_params,
            (
                "tenant-a",
                "workbench_relation.read_model.refresh:bank_detail:2026-02",
                "event-1",
                13357,
                created_at,
                created_at,
                "event-1",
            ),
        )
        self.assertEqual(
            resolve_params,
            (
                "workbench_relation_read_model_not_fresh",
                0.25,
                "worker-1",
                locked_at,
                "event-2",
                "pending",
                13358,
                "event-1",
                "worker-1",
            ),
        )

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
        self.assertEqual(params, ("temporary", 45, "event-1", "worker-1"))

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

    def test_runtime_queue_history_retention_preview_counts_done_history_without_delete(self) -> None:
        transaction = FakeTransaction(
            rows=[
                [{"event_type": "oa.sync", "count": 3}],
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        result = repository.preview_runtime_queue_history_retention(
            keep_days=30,
            keep_recent_per_type=512,
            limit=20_000,
        )

        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["outbox_events"]["candidate_count"], 3)
        self.assertEqual(result["outbox_events"]["counts_by_event_type"], {"oa.sync": 3})
        self.assertEqual([call[0] for call in transaction.calls], ["fetch_all"])
        outbox_sql, outbox_params = transaction.calls[0][1], transaction.calls[0][2]
        normalized_outbox_sql = " ".join(outbox_sql.lower().split())
        self.assertIn("from job.outbox_events event", normalized_outbox_sql)
        self.assertIn("event.status = 'done'", normalized_outbox_sql)
        self.assertIn("blocker.status in ('failed', 'dead_lettered')", normalized_outbox_sql)
        self.assertNotIn("delete from job.outbox_events", normalized_outbox_sql)
        self.assertEqual(outbox_params, (30, 512, 20_000))
        self.assertEqual(transaction.outcomes, ["commit"])

    def test_runtime_queue_history_retention_execute_deletes_only_candidates(self) -> None:
        transaction = FakeTransaction(
            rows=[
                [{"event_type": "oa.sync", "count": 7}],
            ]
        )
        repository = RuntimeQueueRepository(FakeConnection(transaction))

        result = repository.prune_runtime_queue_history(
            keep_days=0,
            keep_recent_per_type=1,
            limit=100,
        )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["outbox_events"]["deleted_count"], 7)
        outbox_sql = " ".join(transaction.calls[0][1].lower().split())
        self.assertIn("delete from job.outbox_events", outbox_sql)
        self.assertIn("where event.id = candidates.id", outbox_sql)
        self.assertEqual(transaction.calls[0][2], (0, 1, 100))

    def test_runtime_queue_history_retention_rejects_invalid_policy(self) -> None:
        repository = RuntimeQueueRepository(FakeConnection(FakeTransaction()))

        with self.assertRaises(RuntimeQueueDataError):
            repository.preview_runtime_queue_history_retention(keep_days=-1)
        with self.assertRaises(RuntimeQueueDataError):
            repository.preview_runtime_queue_history_retention(keep_recent_per_type=0)
        with self.assertRaises(RuntimeQueueDataError):
            repository.preview_runtime_queue_history_retention(limit=0)


if __name__ == "__main__":
    unittest.main()
