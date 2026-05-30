from __future__ import annotations

import importlib
import unittest
from dataclasses import dataclass, field
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
    payload: dict[str, object] = field(default_factory=dict)


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
                "event_type": "workbench.read_model.refresh",
                "aggregate_type": "read_model",
                "aggregate_id": "2026-05",
                "scope_type": "workbench",
                "scope_key": "2026-05",
                "dedupe_key": "workbench.read_model.refresh:workbench:2026-05",
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

    def enqueue_refresh(self, *, transaction: object, scope_type: str, scope_key: str, reason: str) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("forced outbox failure")
        event = {
            "event_id": f"event-{len(self.calls) + 1}",
            "scope_type": scope_type,
            "scope_key": scope_key,
            "source_version": len(self.calls) + 1,
            "reason": reason,
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


class WorkbenchUoWContractTests(unittest.TestCase):
    def _transaction_bound_writer(self) -> Callable[..., object]:
        method = getattr(RuntimeQueueRepository, "enqueue_read_model_refresh_in_transaction", None)
        if callable(method):
            repository = RuntimeQueueRepository(_NestedTransactionForbiddenConnection())  # type: ignore[arg-type]
            return method.__get__(repository, RuntimeQueueRepository)

        try:
            module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        except ModuleNotFoundError as exc:
            if exc.name == "fin_ops_platform.services.workbench_uow":
                self.fail(
                    "PF-P019 target missing: provide a transaction-bound read model refresh writer "
                    "or RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction(transaction=...)."
                )
            raise
        writer_class = getattr(module, "TransactionBoundReadModelRefreshWriter", None)
        if writer_class is None:
            self.fail(
                "PF-P019 target missing: fin_ops_platform.services.workbench_uow."
                "TransactionBoundReadModelRefreshWriter."
            )
        writer = writer_class()
        enqueue = getattr(writer, "enqueue_refresh", None)
        if not callable(enqueue):
            self.fail("TransactionBoundReadModelRefreshWriter must expose enqueue_refresh(transaction=...).")
        return enqueue

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

    def test_read_model_refresh_writer_uses_supplied_transaction_without_opening_nested_transaction(self) -> None:
        enqueue = self._transaction_bound_writer()
        transaction = _RecordingTransaction()

        event = enqueue(
            transaction=transaction,
            scope_type="workbench",
            scope_key="2026-05",
            reason="confirm_link",
            tenant_id="default",
            trace_id="trace-1",
        )

        self.assertEqual(getattr(event, "source_version", None) or event["source_version"], 7)

    def test_read_model_refresh_writer_bumps_source_version_and_writes_matching_outbox_payload(self) -> None:
        enqueue = self._transaction_bound_writer()
        transaction = _RecordingTransaction(dirty_source_version=8)

        event = enqueue(
            transaction=transaction,
            scope_type="workbench",
            scope_key="2026-05",
            reason="exception_apply",
            tenant_id="default",
            trace_id="trace-1",
        )

        event_payload = getattr(event, "payload", None) or event["payload"]
        self.assertEqual(event_payload["source_version"], 8)
        self.assertEqual(getattr(event, "source_version", None) or event["source_version"], 8)
        self.assertEqual(event_payload["scope_type"], "workbench")
        self.assertEqual(event_payload["scope_key"], "2026-05")

    def test_read_model_refresh_writer_failure_rolls_back_transaction(self) -> None:
        connection = _RecordingConnection(_RecordingTransaction(fail_on_outbox=True))
        enqueue = self._transaction_bound_writer()

        with self.assertRaises(RuntimeError):
            with connection.transaction() as transaction:
                enqueue(
                    transaction=transaction,
                    scope_type="workbench",
                    scope_key="2026-05",
                    reason="confirm_link",
                    tenant_id="default",
                    trace_id="trace-1",
                )

        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

    def test_confirm_link_commits_pair_relation_history_dirty_scope_and_outbox_in_one_transaction(self) -> None:
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
        self.assertEqual(writer.calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(result["source_versions"]["2026-05"], 1)
        self.assertEqual(result["outbox_event_ids"], ["event-1"])

    def test_confirm_link_outbox_failure_rolls_back_pair_relation_and_history(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter(fail=True)
        uow = self._new_uow(connection=connection, read_model_writer=writer)

        def handler(ctx: object) -> dict[str, object]:
            ctx.pair_relations.record("save_relation", case_id="CASE-ROLLBACK")
            ctx.pair_relations.record("append_history", case_id="CASE-ROLLBACK")
            return {"case_id": "CASE-ROLLBACK", "affected_scope_keys": ["2026-05"]}

        with self.assertRaises(RuntimeError):
            self._run_uow(uow, _Command(action_name="confirm_link", scope_keys=["2026-05"]), handler)

        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

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
        self.assertEqual(writer.calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(result["source_versions"]["2026-05"], 1)

    def test_personal_advance_repayment_rolls_back_case_and_relation_when_dirty_scope_fails(self) -> None:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter(fail=True)
        uow = self._new_uow(connection=connection, read_model_writer=writer)

        def handler(ctx: object) -> dict[str, object]:
            ctx.exception_cases.record("save_settlement_case", case_id="PERSONAL-1")
            ctx.pair_relations.record("save_relation", case_id="PERSONAL-1")
            return {"case_id": "PERSONAL-1", "affected_scope_keys": ["2026-05"]}

        with self.assertRaises(RuntimeError):
            self._run_uow(
                uow,
                _Command(action_name="confirm_personal_advance_repayment", scope_keys=["2026-05"]),
                handler,
            )

        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)

    # PF-P021-CI: target contract tests stay visible in default CI as
    # expected failures until the corresponding UoW semantics are implemented.
    @unittest.expectedFailure
    def test_withdraw_submit_rejects_stale_preview_relation_version(self) -> None:
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
                    action_name="withdraw_link",
                    expected_versions={"relation:CASE-1": 3},
                    payload={"current_relation_version": 4},
                ),
                handler,
            )
        self.assertFalse(called)

    @unittest.expectedFailure
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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
    def test_confirm_link_idempotency_key_replays_first_result_without_duplicate_history(self) -> None:
        idempotency = _RecordingIdempotencyStore()
        uow = self._new_uow(idempotency_store=idempotency)
        call_count = 0

        def handler(ctx: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            ctx.pair_relations.record("append_history", case_id="CASE-IDEMPOTENT")
            return {"case_id": "CASE-IDEMPOTENT", "affected_scope_keys": ["2026-05"]}

        command = _Command(action_name="confirm_link", scope_keys=["2026-05"], idempotency_key="confirm:idem-1")
        first = self._run_uow(uow, command, handler)
        second = self._run_uow(uow, command, handler)

        self.assertEqual(first, second)
        self.assertEqual(call_count, 1)

    @unittest.expectedFailure
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
        )
        self._run_uow(uow, command, handler)
        self._run_uow(uow, command, handler)

        self.assertEqual(call_count, 1)
        self.assertEqual(len(writer.calls), 1)

    @unittest.expectedFailure
    def test_cash_special_idempotency_key_does_not_append_duplicate_history(self) -> None:
        uow = self._new_uow()
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
        )
        self._run_uow(uow, command, handler)
        self._run_uow(uow, command, handler)

        self.assertEqual(history_appends, 1)

    def test_outbox_payload_contains_source_version_for_each_dirty_scope(self) -> None:
        connection = _RecordingConnection(_RecordingTransaction(dirty_source_version=9))
        repository = RuntimeQueueRepository(connection)  # type: ignore[arg-type]

        event = repository.enqueue_read_model_refresh(
            scope_type="workbench",
            scope_key="2026-05",
            reason="confirm_link",
            tenant_id="default",
            trace_id="trace-1",
        )

        self.assertEqual(event.source_version, 9)
        self.assertEqual(event.payload["source_version"], 9)
        self.assertEqual(event.payload["scope_type"], "workbench")
        self.assertEqual(event.payload["scope_key"], "2026-05")

    def test_worker_completion_cannot_mark_newer_dirty_scope_done_from_older_event(self) -> None:
        transaction = _RecordingTransaction()
        connection = _RecordingConnection(transaction)
        repository = RuntimeQueueRepository(connection)  # type: ignore[arg-type]

        result = repository.complete_read_model_refresh(
            tenant_id="default",
            scope_type="workbench",
            scope_key="2026-05",
            source_version=2,
        )

        self.assertFalse(result)
        self.assertEqual(connection.commits, 1)
        self.assertTrue(any("source_version <= %s" in sql for _, sql, _ in transaction.calls))


if __name__ == "__main__":
    unittest.main()
