from __future__ import annotations

import importlib
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable

from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository


"""
PF-P019 target contract tests.

These tests intentionally describe the Workbench write Unit of Work target state.
The current implementation is allowed to fail this file during the red phase, but
failures must point to missing UoW / transaction-bound writer capability rather
than syntax errors, import errors, or real external services.
"""


@dataclass
class _Command:
    action_name: str
    scope_keys: list[str] = field(default_factory=list)
    expected_versions: dict[str, object] = field(default_factory=dict)
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    tenant_id: str = "default"
    actor_id: str = "system"
    payload: dict[str, object] = field(default_factory=dict)
    refresh_metadata: dict[str, object] | None = None


class _RecordingTransaction:
    def __init__(self, *, dirty_source_version: int = 7, fail_on_outbox: bool = False) -> None:
        self.dirty_source_version = dirty_source_version
        self.fail_on_outbox = fail_on_outbox
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.last_outbox_payload: dict[str, object] | None = None

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        normalized = " ".join(sql.lower().split())
        self.calls.append(("fetch_one", normalized, params))
        if "job.read_model_dirty_scopes" in normalized and normalized.startswith("insert into"):
            return {"source_version": self.dirty_source_version}
        if "job.outbox_events" in normalized and normalized.startswith("insert into"):
            if self.fail_on_outbox:
                raise RuntimeError("forced outbox failure")
            payload = params[-2] if len(params) >= 2 else {}
            if isinstance(payload, dict):
                self.last_outbox_payload = payload
            return {
                "event_id": "event-1",
                "tenant_id": "default",
                "event_type": "cost_statistics.fact.changed",
                "aggregate_type": "canonical_fact",
                "aggregate_id": "2026-05",
                "scope_type": "cost_statistics",
                "scope_key": "2026-05",
                "dedupe_key": "cost_statistics.fact.changed:cost_statistics:2026-05",
                "payload": payload if isinstance(payload, dict) else {},
                "attempts": 0,
                "status": "pending",
                "schema_version": 1,
                "source_version": self.dirty_source_version,
                "priority": "normal",
                "trace_id": "trace-1",
            }
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        normalized = " ".join(sql.lower().split())
        self.calls.append(("execute", normalized, params))
        return 1


class _TransactionContext:
    def __init__(self, owner: _RecordingConnection, transaction: _RecordingTransaction) -> None:
        self._owner = owner
        self._transaction = transaction

    def __enter__(self) -> _RecordingTransaction:
        self._owner.opened += 1
        return self._transaction

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is None:
            self._owner.commits += 1
        else:
            self._owner.rollbacks += 1
        return False


class _RecordingConnection:
    def __init__(self, transaction: _RecordingTransaction | None = None) -> None:
        self.transaction_obj = transaction or _RecordingTransaction()
        self.opened = 0
        self.commits = 0
        self.rollbacks = 0

    def transaction(self) -> _TransactionContext:
        return _TransactionContext(self, self.transaction_obj)


class _NestedTransactionForbiddenConnection:
    def __init__(self) -> None:
        self.transaction_open_count = 0

    def transaction(self) -> object:
        self.transaction_open_count += 1
        raise AssertionError("transaction-bound writer must not open its own connection.transaction()")


class _RecordingRepositoryFactory:
    def __init__(self) -> None:
        self.created_for_transactions: list[object] = []

    def __call__(self, transaction: object) -> SimpleNamespace:
        self.created_for_transactions.append(transaction)
        return SimpleNamespace(
            pair_relations=_RepositoryPort("pair_relations", transaction),
            exception_cases=_RepositoryPort("exception_cases", transaction),
            row_overrides=_RepositoryPort("row_overrides", transaction),
            candidate_matches=_RepositoryPort("candidate_matches", transaction),
        )


class _RepositoryPort:
    def __init__(self, name: str, transaction: object) -> None:
        self.name = name
        self.transaction = transaction
        self.calls: list[tuple[str, dict[str, object]]] = []

    def record(self, operation: str, **payload: object) -> None:
        self.calls.append((operation, dict(payload)))


class _RecordingDirtyOutboxWriter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def enqueue_refresh(
        self,
        *,
        transaction: object,
        scope_type: str,
        scope_key: str,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("forced outbox failure")
        event = {
            "event_id": f"event-{len(self.calls) + 1}",
            "scope_type": scope_type,
            "scope_key": scope_key,
            "source_version": len(self.calls) + 1,
            "reason": reason,
            "metadata": dict(metadata or {}),
        }
        self.calls.append({"transaction": transaction, **event})
        return event


class _RecordingIdempotencyStore:
    def __init__(self) -> None:
        self.records: dict[str, object] = {}
        self.reserved: list[str] = []

    def get(self, key: str) -> object | None:
        return self.records.get(key)

    def reserve(self, key: str) -> None:
        self.reserved.append(key)

    def commit(self, key: str, result: object) -> None:
        self.records[key] = result


class _TransactionBoundIdempotencyStore:
    def __init__(self, root: "_TransactionAwareIdempotencyStore", transaction: object) -> None:
        self._root = root
        self._transaction = transaction

    def reserve(self, **kwargs: object) -> None:
        self._root.reserve_calls.append({"transaction": self._transaction, **kwargs})

    def commit(self, **kwargs: object) -> None:
        self._root.commit_calls.append({"transaction": self._transaction, **kwargs})


class _ExistingReservedTransactionBoundIdempotencyStore:
    def __init__(self, root: "_ExistingReservedIdempotencyStore", transaction: object) -> None:
        self._root = root
        self._transaction = transaction

    def reserve(self, **kwargs: object) -> object:
        self._root.reserve_calls.append({"transaction": self._transaction, **kwargs})
        record = self._root.record
        return SimpleNamespace(record=record, created=False)

    def commit(self, **kwargs: object) -> None:
        self._root.commit_calls.append({"transaction": self._transaction, **kwargs})


class _TransactionAwareIdempotencyStore:
    def __init__(self) -> None:
        self.get_calls: list[dict[str, object]] = []
        self.bound_transactions: list[object] = []
        self.reserve_calls: list[dict[str, object]] = []
        self.commit_calls: list[dict[str, object]] = []

    def get_committed_or_reserved(self, *args: object, **kwargs: object) -> object | None:
        if args:
            tenant_id, actor_id, idempotency_key = args
        else:
            tenant_id = kwargs["tenant_id"]
            actor_id = kwargs["actor_id"]
            idempotency_key = kwargs["idempotency_key"]
        self.get_calls.append(
            {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
            }
        )
        return None

    def for_transaction(self, transaction: object) -> _TransactionBoundIdempotencyStore:
        self.bound_transactions.append(transaction)
        return _TransactionBoundIdempotencyStore(self, transaction)

    def reserve(self, **_: object) -> None:
        raise AssertionError("durable idempotency reserve must use the transaction-bound store")

    def commit(self, **_: object) -> None:
        raise AssertionError("durable idempotency commit must use the transaction-bound store")


class _ExistingReservedIdempotencyStore:
    def __init__(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        record_class = getattr(module, "WorkbenchIdempotencyRecord")
        self.record = record_class(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:existing-reserved",
            request_fingerprint="fp:confirm:existing-reserved",
            status="reserved",
        )
        self.bound_transactions: list[object] = []
        self.reserve_calls: list[dict[str, object]] = []
        self.commit_calls: list[dict[str, object]] = []

    def get_committed_or_reserved(self, *args: object, **kwargs: object) -> object | None:
        return None

    def for_transaction(self, transaction: object) -> _ExistingReservedTransactionBoundIdempotencyStore:
        self.bound_transactions.append(transaction)
        return _ExistingReservedTransactionBoundIdempotencyStore(self, transaction)


class _ExpiredReservedTransactionBoundIdempotencyStore:
    def __init__(self, root: "_ExpiredReservedIdempotencyStore", transaction: object) -> None:
        self._root = root
        self._transaction = transaction

    def reserve(self, **kwargs: object) -> object:
        self._root.reserve_calls.append({"transaction": self._transaction, **kwargs})
        return SimpleNamespace(record=self._root.taken_over_record, created=False, taken_over_expired=True)

    def commit(self, **kwargs: object) -> None:
        self._root.commit_calls.append({"transaction": self._transaction, **kwargs})


class _ExpiredReservedIdempotencyStore:
    def __init__(self, *, request_fingerprint: str = "fp:confirm:expired") -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        record_class = getattr(module, "WorkbenchIdempotencyRecord")
        self.record = record_class(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:expired",
            request_fingerprint=request_fingerprint,
            status="reserved",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        self.taken_over_record = record_class(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:expired",
            request_fingerprint=request_fingerprint,
            status="reserved",
            request_payload={"case_id": "CASE-RETRY"},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        self.bound_transactions: list[object] = []
        self.reserve_calls: list[dict[str, object]] = []
        self.commit_calls: list[dict[str, object]] = []

    def get_committed_or_reserved(self, *args: object, **kwargs: object) -> object | None:
        return self.record

    def for_transaction(self, transaction: object) -> _ExpiredReservedTransactionBoundIdempotencyStore:
        self.bound_transactions.append(transaction)
        return _ExpiredReservedTransactionBoundIdempotencyStore(self, transaction)


class _ExistingFailedIdempotencyStore:
    def __init__(self, *, request_fingerprint: str = "fp:confirm:failed") -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        record_class = getattr(module, "WorkbenchIdempotencyRecord")
        self.record = record_class(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:failed",
            request_fingerprint=request_fingerprint,
            status="failed",
            response_payload={"error": "previous_failure"},
        )
        self.bound_transactions: list[object] = []
        self.reserve_calls: list[dict[str, object]] = []
        self.commit_calls: list[dict[str, object]] = []

    def get_committed_or_reserved(self, *args: object, **kwargs: object) -> object | None:
        return self.record

    def for_transaction(self, transaction: object) -> object:
        self.bound_transactions.append(transaction)
        raise AssertionError("failed idempotency records must not enter a transaction")


class WorkbenchUoWContractTests(unittest.TestCase):
    def _uow_class(self) -> type:
        try:
            module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        except ModuleNotFoundError as exc:
            if exc.name == "fin_ops_platform.services.workbench_uow":
                self.fail(
                    "PF-P019 target missing: fin_ops_platform.services.workbench_uow.WorkbenchWriteUnitOfWork."
                )
            raise
        cls = getattr(module, "WorkbenchWriteUnitOfWork", None)
        if cls is None:
            self.fail("PF-P019 target missing: WorkbenchWriteUnitOfWork.")
        return cls

    def _new_uow(
        self,
        *,
        connection: _RecordingConnection | None = None,
        read_model_writer: _RecordingDirtyOutboxWriter | None = None,
        idempotency_store: _RecordingIdempotencyStore | None = None,
        repository_factory: _RecordingRepositoryFactory | None = None,
    ) -> object:
        cls = self._uow_class()
        try:
            return cls(
                connection=connection or _RecordingConnection(),
                repository_factory=repository_factory or _RecordingRepositoryFactory(),
                read_model_refresh_writer=read_model_writer or _RecordingDirtyOutboxWriter(),
                idempotency_store=idempotency_store or _RecordingIdempotencyStore(),
            )
        except TypeError as exc:
            self.fail(
                "WorkbenchWriteUnitOfWork constructor must accept connection, repository_factory, "
                f"read_model_refresh_writer, and idempotency_store. Got: {exc}"
            )

    def _run_uow(self, uow: object, command: _Command, handler: Callable[[object], object]) -> object:
        run = getattr(uow, "run", None)
        if not callable(run):
            self.fail("WorkbenchWriteUnitOfWork must expose run(command, handler).")
        try:
            return run(command, handler)
        except TypeError as exc:
            self.fail(f"WorkbenchWriteUnitOfWork.run must accept command and handler. Got: {exc}")

    def test_read_model_refresh_writer_is_removed_from_workbench_uow(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")

        self.assertFalse(hasattr(RuntimeQueueRepository, "enqueue_read_model_refresh_in_transaction"))
        self.assertFalse(hasattr(module, "RuntimeQueueReadModelRefreshWriter"))
        self.assertFalse(hasattr(module, "TransactionBoundReadModelRefreshWriter"))

    def test_confirm_link_commits_pair_relation_history_without_page_read_model_outbox(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        factory = _RecordingRepositoryFactory()
        uow = self._new_uow(connection=connection, read_model_writer=writer, repository_factory=factory)

        def handler(ctx: object) -> dict[str, object]:
            self.assertIs(ctx.pair_relations.transaction, ctx.transaction)
            ctx.pair_relations.record("save_relation", case_id="CASE-1")
            ctx.pair_relations.record("append_history", case_id="CASE-1")
            return {"case_id": "CASE-1", "affected_scope_keys": ["2026-05"]}

        result = self._run_uow(
            uow,
            _Command(action_name="confirm_link", scope_keys=["2026-05"], idempotency_key="confirm:CASE-1"),
            handler,
        )

        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertEqual(writer.calls, [])
        self.assertEqual(result["source_versions"], {})
        self.assertEqual(result["outbox_event_ids"], [])

    def test_confirm_link_preserves_relation_refresh_metadata_in_transactional_outbox(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        uow = self._new_uow(connection=connection, read_model_writer=writer)

        def handler(ctx: object) -> dict[str, object]:
            ctx.pair_relations.record("save_relation", case_id="CASE-1")
            return {"case_id": "CASE-1", "affected_scope_keys": ["2026-05"]}

        result = self._run_uow(
            uow,
            _Command(
                action_name="confirm_link",
                scope_keys=["2026-05"],
                refresh_metadata={
                    "source": "confirm_link",
                    "case_id": "CASE-1",
                    "downstream_scope_types": ["bank_detail", "pending_invoice"],
                    "invoice_usage_scope_types": ["input_invoice_usage"],
                    "pending_invoice_scope_keys": ["expense:all:2026-05"],
                },
            ),
            handler,
        )

        self.assertEqual(result["outbox_event_ids"], [])
        self.assertEqual(writer.calls, [])

    def test_confirm_link_ignores_removed_outbox_writer_failure(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter(fail=True)
        uow = self._new_uow(connection=connection, read_model_writer=writer)

        def handler(ctx: object) -> dict[str, object]:
            ctx.pair_relations.record("save_relation", case_id="CASE-ROLLBACK")
            ctx.pair_relations.record("append_history", case_id="CASE-ROLLBACK")
            return {"case_id": "CASE-ROLLBACK", "affected_scope_keys": ["2026-05"]}

        self._run_uow(uow, _Command(action_name="confirm_link", scope_keys=["2026-05"]), handler)

        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)

    def test_exception_apply_commits_case_override_candidate_dirty_scope_and_outbox_in_one_transaction(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        uow = self._new_uow(connection=connection, read_model_writer=writer)

        def handler(ctx: object) -> dict[str, object]:
            ctx.exception_cases.record("save_case", case_id="EX-1")
            ctx.row_overrides.record("save_override", row_id="bank-1")
            ctx.candidate_matches.record("replace_best_effort", row_id="bank-1")
            return {"case_id": "EX-1", "affected_scope_keys": ["2026-05"]}

        result = self._run_uow(
            uow,
            _Command(action_name="exception_apply", scope_keys=["2026-05"], idempotency_key="exception:EX-1"),
            handler,
        )

        self.assertEqual(connection.commits, 1)
        self.assertEqual(writer.calls, [])
        self.assertEqual(result["source_versions"], {})

    def test_personal_advance_repayment_commits_without_removed_dirty_scope_writer(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter(fail=True)
        uow = self._new_uow(connection=connection, read_model_writer=writer)

        def handler(ctx: object) -> dict[str, object]:
            ctx.exception_cases.record("save_settlement_case", case_id="PERSONAL-1")
            ctx.pair_relations.record("save_relation", case_id="PERSONAL-1")
            return {"case_id": "PERSONAL-1", "affected_scope_keys": ["2026-05"]}

        self._run_uow(
            uow,
            _Command(action_name="confirm_personal_advance_repayment", scope_keys=["2026-05"]),
            handler,
        )

        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)

    def test_withdraw_submit_rejects_stale_preview_relation_version(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency = _RecordingIdempotencyStore()
        uow = self._new_uow(connection=connection, read_model_writer=writer, idempotency_store=idempotency)
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "409|stale|conflict|version"):
            self._run_uow(
                uow,
                _Command(
                    action_name="withdraw_link",
                    expected_versions={"relation:CASE-1": 3},
                    idempotency_key="withdraw:stale-preview",
                    payload={"current_relation_version": 4},
                ),
                handler,
            )
        self.assertFalse(called)
        self.assertEqual(writer.calls, [])
        self.assertEqual(idempotency.reserved, [])
        self.assertEqual(idempotency.records, {})
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

    def test_cancel_link_rejects_stale_replaced_relation(self) -> None:
        uow = self._new_uow()
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "409|stale|conflict|version"):
            self._run_uow(
                uow,
                _Command(
                    action_name="cancel_link",
                    expected_versions={"relation:CASE-OLD": 2},
                    payload={"current_relation_case_id": "CASE-NEW", "current_relation_version": 5},
                ),
                handler,
            )
        self.assertFalse(called)

    def test_ignore_row_rejects_when_row_already_confirmed(self) -> None:
        uow = self._new_uow()
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "409|stale|conflict|already"):
            self._run_uow(
                uow,
                _Command(
                    action_name="ignore_row",
                    expected_versions={"row:invoice-1": "open", "relation:CASE-CONFIRMED": None},
                    payload={"current_row_status": "confirmed"},
                ),
                handler,
            )
        self.assertFalse(called)

    def test_cash_special_rejects_changed_relation_version(self) -> None:
        uow = self._new_uow()
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "409|stale|conflict|version"):
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_cash_pass_through",
                    expected_versions={"relation:CASE-CASH": 1},
                    payload={"current_relation_case_id": "CASE-CASH", "current_relation_version": 2},
                ),
                handler,
            )
        self.assertFalse(called)

    def test_confirm_link_idempotency_key_replays_first_result_without_duplicate_history(self) -> None:
        idempotency = _RecordingIdempotencyStore()
        uow = self._new_uow(idempotency_store=idempotency)
        call_count = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            ctx.pair_relations.record("append_history", case_id="CASE-IDEMPOTENT")
            return {"case_id": "CASE-IDEMPOTENT", "affected_scope_keys": ["2026-05"]}

        command = _Command(
            action_name="confirm_link",
            scope_keys=["2026-05"],
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp:confirm-link:case-idempotent",
            actor_id="finance-1",
            payload={"case_id": "CASE-IDEMPOTENT", "row_ids": ["oa-1", "bank-1"]},
        )
        first = self._run_uow(uow, command, handler)
        second = self._run_uow(uow, command, handler)

        self.assertEqual(first, second)
        self.assertEqual(call_count, 1)
        self.assertEqual(idempotency.records.get("confirm:idem-1"), first)

    def test_exception_apply_idempotency_key_replays_first_result_without_duplicate_case_or_outbox(self) -> None:
        idempotency = _RecordingIdempotencyStore()
        writer = _RecordingDirtyOutboxWriter()
        uow = self._new_uow(idempotency_store=idempotency, read_model_writer=writer)
        call_count = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            ctx.exception_cases.record("save_case", case_id="EX-IDEMPOTENT")
            return {"case_id": "EX-IDEMPOTENT", "affected_scope_keys": ["2026-05"]}

        command = _Command(
            action_name="exception_apply",
            scope_keys=["2026-05"],
            idempotency_key="exception:idem-1",
            request_fingerprint="fp:exception-apply:ex-idempotent",
            actor_id="finance-1",
            payload={"case_id": "EX-IDEMPOTENT", "row_ids": ["bank-1"], "scenario_code": "manual"},
        )
        self._run_uow(uow, command, handler)
        self._run_uow(uow, command, handler)

        self.assertEqual(call_count, 1)
        self.assertEqual(writer.calls, [])
        self.assertIn("exception:idem-1", idempotency.records)

    def test_cash_special_idempotency_key_does_not_append_duplicate_history(self) -> None:
        idempotency = _RecordingIdempotencyStore()
        uow = self._new_uow(idempotency_store=idempotency)
        history_appends = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal history_appends
            history_appends += 1
            ctx.pair_relations.record("append_history", case_id="CASE-CASH")
            return {"case_id": "CASE-CASH", "affected_scope_keys": ["2026-05"]}

        command = _Command(
            action_name="confirm_cash_pass_through",
            scope_keys=["2026-05"],
            idempotency_key="cash:idem-1",
            request_fingerprint="fp:cash-special:case-cash",
            actor_id="finance-1",
            payload={"case_id": "CASE-CASH", "bank_row_ids": ["bank-in-1", "bank-out-1"]},
        )
        self._run_uow(uow, command, handler)
        self._run_uow(uow, command, handler)

        self.assertEqual(history_appends, 1)
        self.assertIn("cash:idem-1", idempotency.records)

    def test_idempotency_reserve_and_commit_use_transaction_bound_store(self) -> None:
        connection = _RecordingConnection()
        idempotency = _TransactionAwareIdempotencyStore()
        uow = self._new_uow(connection=connection, idempotency_store=idempotency)  # type: ignore[arg-type]

        def handler(ctx: object) -> dict[str, object]:
            self.assertIs(ctx.idempotency_store._transaction, connection.transaction_obj)
            return {"case_id": "CASE-TX-IDEMPOTENCY", "affected_scope_keys": ["2026-05"]}

        result = self._run_uow(
            uow,
            _Command(
                action_name="confirm_link",
                scope_keys=["2026-05"],
                idempotency_key="confirm:tx-bound",
                request_fingerprint="fp:confirm:tx-bound",
                actor_id="finance-1",
                payload={"case_id": "CASE-TX-IDEMPOTENCY"},
            ),
            handler,
        )

        self.assertEqual(result["case_id"], "CASE-TX-IDEMPOTENCY")
        self.assertEqual(idempotency.bound_transactions, [connection.transaction_obj])
        self.assertEqual(idempotency.reserve_calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(idempotency.commit_calls[0]["transaction"], connection.transaction_obj)

    def test_existing_reserved_transaction_outcome_does_not_execute_handler_dirty_scope_or_commit(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency = _ExistingReservedIdempotencyStore()
        uow = self._new_uow(connection=connection, read_model_writer=writer, idempotency_store=idempotency)  # type: ignore[arg-type]
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "in.progress|idempotency"):
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:existing-reserved",
                    request_fingerprint="fp:confirm:existing-reserved",
                    actor_id="finance-1",
                    payload={"case_id": "CASE-IDEM"},
                ),
                handler,
            )

        self.assertFalse(called)
        self.assertEqual(writer.calls, [])
        self.assertEqual(idempotency.reserve_calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(idempotency.commit_calls, [])
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

    def test_expired_reserved_same_fingerprint_is_taken_over_inside_transaction(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency = _ExpiredReservedIdempotencyStore()
        uow = self._new_uow(connection=connection, read_model_writer=writer, idempotency_store=idempotency)  # type: ignore[arg-type]
        handler_calls = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal handler_calls
            handler_calls += 1
            ctx.pair_relations.record("save_relation", case_id="CASE-RETRY")
            return {"case_id": "CASE-RETRY", "affected_scope_keys": ["2026-05"]}

        result = self._run_uow(
            uow,
            _Command(
                action_name="confirm_link",
                scope_keys=["2026-05"],
                idempotency_key="confirm:expired",
                request_fingerprint="fp:confirm:expired",
                actor_id="finance-1",
                payload={"case_id": "CASE-RETRY", "row_ids": ["oa-1", "bank-1"]},
            ),
            handler,
        )

        self.assertEqual(handler_calls, 1)
        self.assertEqual(result["case_id"], "CASE-RETRY")
        self.assertEqual(idempotency.reserve_calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(idempotency.commit_calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(writer.calls, [])
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)

    def test_expired_reserved_different_fingerprint_still_conflicts_without_takeover(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency = _ExpiredReservedIdempotencyStore(request_fingerprint="fp:confirm:old")
        uow = self._new_uow(connection=connection, read_model_writer=writer, idempotency_store=idempotency)  # type: ignore[arg-type]
        handler_calls = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal handler_calls
            handler_calls += 1
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "idempotency|fingerprint|conflict"):
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:expired",
                    request_fingerprint="fp:confirm:new",
                    actor_id="finance-1",
                    payload={"case_id": "CASE-NEW", "row_ids": ["oa-1", "bank-1"]},
                ),
                handler,
            )

        self.assertEqual(handler_calls, 0)
        self.assertEqual(idempotency.reserve_calls, [])
        self.assertEqual(idempotency.commit_calls, [])
        self.assertEqual(writer.calls, [])
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 0)

    def test_existing_failed_same_fingerprint_returns_failed_without_handler_transaction_or_outbox(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency = _ExistingFailedIdempotencyStore()
        uow = self._new_uow(connection=connection, read_model_writer=writer, idempotency_store=idempotency)  # type: ignore[arg-type]
        handler_calls = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal handler_calls
            handler_calls += 1
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "failed|idempotency") as raised:
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:failed",
                    request_fingerprint="fp:confirm:failed",
                    actor_id="finance-1",
                    payload={"case_id": "CASE-FAILED", "row_ids": ["oa-1", "bank-1"]},
                ),
                handler,
            )

        payload = raised.exception.to_response_payload()
        self.assertEqual(payload["error"], "idempotency_key_failed")
        self.assertFalse(payload["retryable"])
        self.assertEqual(handler_calls, 0)
        self.assertEqual(idempotency.bound_transactions, [])
        self.assertEqual(idempotency.reserve_calls, [])
        self.assertEqual(idempotency.commit_calls, [])
        self.assertEqual(writer.calls, [])
        self.assertEqual(connection.opened, 0)
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 0)

    def test_existing_failed_different_fingerprint_still_conflicts_without_transaction(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency = _ExistingFailedIdempotencyStore(request_fingerprint="fp:confirm:old")
        uow = self._new_uow(connection=connection, read_model_writer=writer, idempotency_store=idempotency)  # type: ignore[arg-type]
        handler_calls = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal handler_calls
            handler_calls += 1
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "idempotency|fingerprint|conflict"):
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:failed",
                    request_fingerprint="fp:confirm:new",
                    actor_id="finance-1",
                    payload={"case_id": "CASE-NEW", "row_ids": ["oa-1", "bank-1"]},
                ),
                handler,
            )

        self.assertEqual(handler_calls, 0)
        self.assertEqual(idempotency.bound_transactions, [])
        self.assertEqual(writer.calls, [])
        self.assertEqual(connection.opened, 0)

if __name__ == "__main__":
    unittest.main()
