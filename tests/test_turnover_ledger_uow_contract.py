from __future__ import annotations

import importlib
import unittest
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable


"""
PF-P053 target contract tests.

These tests intentionally describe the Turnover Ledger write Unit of Work target
state. They started as expectedFailure contracts in PF-P053 and were turned into
ordinary passing tests by the minimal skeleton in PF-P054.
"""


@dataclass
class _Command:
    action_name: str
    scope_keys: list[str] = field(default_factory=lambda: ["all"])
    expected_versions: dict[str, object] = field(default_factory=dict)
    actor_id: str = "finance-user"
    tenant_id: str = "default"
    payload: dict[str, object] = field(default_factory=dict)


class _RecordingTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def record(self, operation: str, **payload: object) -> None:
        self.calls.append((operation, dict(payload)))


class _TransactionContext:
    def __init__(self, owner: "_RecordingConnection", transaction: _RecordingTransaction) -> None:
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


class _RecordingRelationRepository:
    def __init__(self) -> None:
        self.facts: list[dict[str, object]] = []
        self.audit: list[dict[str, object]] = []

    def save_relation(self, relation: dict[str, object], *, transaction: object) -> None:
        self.facts.append({"relation": dict(relation), "transaction": transaction})

    def append_audit(self, event: dict[str, object], *, transaction: object) -> None:
        self.audit.append({"event": dict(event), "transaction": transaction})


class _RecordingExtraRepository:
    def __init__(self) -> None:
        self.extras: list[dict[str, object]] = []

    def save_extra(self, extra: dict[str, object], *, transaction: object) -> None:
        self.extras.append({"extra": dict(extra), "transaction": transaction})


class _RecordingSettingsPort:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []
        self.audit: list[dict[str, object]] = []

    def save_tag_selection(self, payload: dict[str, object], *, transaction: object) -> None:
        self.saved.append({"payload": dict(payload), "transaction": transaction})

    def append_audit(self, event: dict[str, object], *, transaction: object) -> None:
        self.audit.append({"event": dict(event), "transaction": transaction})


class _RecordingBankdetailPort:
    def __init__(self) -> None:
        self.category_updates: list[dict[str, object]] = []

    def apply_turnover_category_updates(self, updates: list[dict[str, object]], *, transaction: object) -> None:
        self.category_updates.append({"updates": list(updates), "transaction": transaction})


class _RecordingDirtyOutboxWriter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def enqueue_refresh(
        self,
        *,
        transaction: object,
        scope_type: str,
        scope_keys: list[str],
        reason: str,
        payload: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        if self.fail:
            raise RuntimeError("forced dirty/outbox failure")
        call = {
            "transaction": transaction,
            "scope_type": scope_type,
            "scope_keys": list(scope_keys),
            "reason": reason,
            "payload": dict(payload or {}),
        }
        self.calls.append(call)
        return [call]


class _StalePreconditionPort:
    def __init__(self, *, stale: bool = False) -> None:
        self.stale = stale
        self.checked: list[dict[str, object]] = []

    def assert_current(self, *, expected_versions: dict[str, object], transaction: object) -> None:
        self.checked.append({"expected_versions": dict(expected_versions), "transaction": transaction})
        if self.stale:
            raise RuntimeError("turnover_write_conflict")


class _RecordingTurnoverExtraSnapshotRepository:
    def __init__(self) -> None:
        self.saved_snapshots: list[dict[str, object]] = []

    def save_turnover_ledger_extras(self, snapshot: dict[str, object]) -> None:
        self.saved_snapshots.append(dict(snapshot))


class _RecordingRepositoryFactory:
    def __init__(self) -> None:
        self.transactions: list[object] = []
        self.repositories: list[_RecordingTurnoverExtraSnapshotRepository] = []

    def __call__(self, transaction: object) -> _RecordingTurnoverExtraSnapshotRepository:
        self.transactions.append(transaction)
        repository = _RecordingTurnoverExtraSnapshotRepository()
        self.repositories.append(repository)
        return repository


class _TransactionOnlyQueueRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue_read_model_refresh_in_transaction(
        self,
        *,
        transaction: object,
        scope_type: str,
        scope_key: str,
        reason: str,
        tenant_id: str,
        priority: str,
        trace_id: str | None,
    ) -> dict[str, object]:
        event = {
            "transaction": transaction,
            "scope_type": scope_type,
            "scope_key": scope_key,
            "reason": reason,
            "tenant_id": tenant_id,
            "priority": priority,
            "trace_id": trace_id,
        }
        self.calls.append(event)
        return event

    def enqueue_read_model_refresh(self, **_kwargs: object) -> None:
        raise AssertionError("non-transaction enqueue must not be used")


class _NonTransactionalQueueRepository:
    def enqueue_read_model_refresh(self, **_kwargs: object) -> None:
        return None


class _RecordingRelationExtraRowProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, *, relation_id: str, extra: dict[str, object]) -> dict[str, object]:
        self.calls.append({"relation_id": relation_id, "extra": dict(extra)})
        return {
            "relation_id": relation_id,
            "note": extra.get("note"),
            "interest_rate_type": extra.get("interest_rate_type", "none"),
        }


class TurnoverLedgerUoWContractTests(unittest.TestCase):
    def _uow_class(self) -> type:
        module = importlib.import_module("fin_ops_platform.services.turnover_ledger_write_uow")
        return getattr(module, "TurnoverLedgerWriteUnitOfWork")

    def _write_facade_class(self) -> type:
        module = importlib.import_module("fin_ops_platform.services.turnover_ledger_write_facade")
        return getattr(module, "TurnoverLedgerWriteFacade")

    def _write_adapters_module(self) -> object:
        return importlib.import_module("fin_ops_platform.services.turnover_ledger_write_adapters")

    def _build_uow(
        self,
        *,
        connection: _RecordingConnection | None = None,
        relation_repository: _RecordingRelationRepository | None = None,
        extra_repository: _RecordingExtraRepository | None = None,
        settings_port: _RecordingSettingsPort | None = None,
        bankdetail_port: _RecordingBankdetailPort | None = None,
        dirty_outbox_writer: _RecordingDirtyOutboxWriter | None = None,
        stale_precondition_port: _StalePreconditionPort | None = None,
    ) -> tuple[object, SimpleNamespace]:
        dependencies = SimpleNamespace(
            connection=connection or _RecordingConnection(),
            relation_repository=relation_repository or _RecordingRelationRepository(),
            extra_repository=extra_repository or _RecordingExtraRepository(),
            settings_port=settings_port or _RecordingSettingsPort(),
            bankdetail_port=bankdetail_port or _RecordingBankdetailPort(),
            dirty_outbox_writer=dirty_outbox_writer or _RecordingDirtyOutboxWriter(),
            stale_precondition_port=stale_precondition_port or _StalePreconditionPort(),
        )
        uow = self._uow_class()(
            connection=dependencies.connection,
            relation_repository=dependencies.relation_repository,
            extra_repository=dependencies.extra_repository,
            settings_port=dependencies.settings_port,
            bankdetail_port=dependencies.bankdetail_port,
            dirty_outbox_writer=dependencies.dirty_outbox_writer,
            stale_precondition_port=dependencies.stale_precondition_port,
        )
        return uow, dependencies

    def _run_uow(self, uow: object, command: _Command, handler: Callable[[object], object]) -> object:
        run = getattr(uow, "run", None)
        if not callable(run):
            self.fail("TurnoverLedgerWriteUnitOfWork must expose run(command, handler).")
        return run(command, handler)

    def test_confirm_relation_commits_relation_audit_dirty_scope_and_outbox_in_one_transaction(self) -> None:
        uow, deps = self._build_uow()

        def handler(context: object) -> dict[str, object]:
            transaction = getattr(context, "transaction")
            deps.relation_repository.save_relation({"relation_id": "turnover_rel_1"}, transaction=transaction)
            deps.relation_repository.append_audit({"action": "confirm_relation"}, transaction=transaction)
            return {"relation_id": "turnover_rel_1"}

        result = self._run_uow(
            uow,
            _Command(action_name="confirm_relation", scope_keys=["all"]),
            handler,
        )

        self.assertEqual(result, {"relation_id": "turnover_rel_1"})
        self.assertEqual(deps.connection.opened, 1)
        self.assertEqual(deps.connection.commits, 1)
        self.assertEqual(deps.connection.rollbacks, 0)
        self.assertEqual(len(deps.relation_repository.facts), 1)
        self.assertEqual(len(deps.relation_repository.audit), 1)
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["scope_type"], "turnover_ledger")
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["reason"], "confirm_relation")

    def test_confirm_relation_outbox_failure_rolls_back_relation_fact_and_audit(self) -> None:
        uow, deps = self._build_uow(dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True))

        def handler(context: object) -> dict[str, object]:
            transaction = getattr(context, "transaction")
            deps.relation_repository.save_relation({"relation_id": "turnover_rel_1"}, transaction=transaction)
            deps.relation_repository.append_audit({"action": "confirm_relation"}, transaction=transaction)
            return {"relation_id": "turnover_rel_1"}

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            self._run_uow(uow, _Command(action_name="confirm_relation", scope_keys=["all"]), handler)

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_withdraw_relation_rejects_stale_or_duplicate_submit_before_handler_runs(self) -> None:
        uow, deps = self._build_uow(stale_precondition_port=_StalePreconditionPort(stale=True))
        handler_called = False

        def handler(_context: object) -> dict[str, object]:
            nonlocal handler_called
            handler_called = True
            return {"relation_id": "turnover_rel_1", "status": "withdrawn"}

        with self.assertRaisesRegex(RuntimeError, "turnover_write_conflict"):
            self._run_uow(
                uow,
                _Command(
                    action_name="withdraw_relation",
                    expected_versions={"relation:turnover_rel_1": 3},
                    payload={"relation_id": "turnover_rel_1"},
                ),
                handler,
            )

        self.assertFalse(handler_called)
        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_relation_extra_outbox_failure_does_not_return_best_effort_success(self) -> None:
        uow, deps = self._build_uow(dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True))

        def handler(context: object) -> dict[str, object]:
            deps.extra_repository.save_extra(
                {"relation_id": "turnover_rel_1", "note": "must be atomic"},
                transaction=getattr(context, "transaction"),
            )
            return {"relation_id": "turnover_rel_1", "note": "must be atomic"}

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            self._run_uow(uow, _Command(action_name="relation_extra_update", scope_keys=["all"]), handler)

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_tag_selection_outbox_failure_rolls_back_settings_save_and_audit(self) -> None:
        uow, deps = self._build_uow(dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True))

        def handler(context: object) -> dict[str, object]:
            transaction = getattr(context, "transaction")
            deps.settings_port.save_tag_selection({"selected_tag_codes": ["external_rule_borrow_out"]}, transaction=transaction)
            deps.settings_port.append_audit({"action": "turnover_ledger_tag_selection_changed"}, transaction=transaction)
            return {"selected_tag_codes": ["external_rule_borrow_out"]}

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            self._run_uow(uow, _Command(action_name="tag_selection_update", scope_keys=["all"]), handler)

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_bank_row_tags_batch_uses_explicit_bankdetail_port_and_rolls_back_on_outbox_failure(self) -> None:
        uow, deps = self._build_uow(dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True))

        def handler(context: object) -> dict[str, object]:
            deps.bankdetail_port.apply_turnover_category_updates(
                [{"transaction_id": "bank_txn_1", "category_code": "borrow_in_company_pending_repayment"}],
                transaction=getattr(context, "transaction"),
            )
            return {"updated_transaction_ids": ["bank_txn_1"]}

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            self._run_uow(uow, _Command(action_name="bank_row_tags_batch", scope_keys=["all"]), handler)

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_uow_constructor_requires_granular_ports_not_application_god_object(self) -> None:
        uow_class = self._uow_class()

        with self.assertRaises(TypeError):
            uow_class(application=object())

    def test_relation_extra_write_facade_constructor_rejects_application_god_object(self) -> None:
        # PF-P056 target contract: PF-P057 should implement the facade and remove this expectedFailure.
        facade_class = self._write_facade_class()

        with self.assertRaises(TypeError):
            facade_class(application=object())

    def test_relation_extra_write_facade_commits_extra_and_dirty_outbox_in_one_uow(self) -> None:
        # PF-P056 target contract: facade must remain service-layer only and delegate transaction scope to UoW.
        uow, deps = self._build_uow()
        facade = self._write_facade_class()(uow=uow)

        result = facade.update_relation_extra(
            relation_id="turnover_rel_1",
            payload={"note": "facade note"},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
        )

        self.assertEqual(deps.connection.opened, 1)
        self.assertEqual(deps.connection.commits, 1)
        self.assertEqual(deps.connection.rollbacks, 0)
        self.assertEqual(len(deps.extra_repository.extras), 1)
        self.assertIs(deps.extra_repository.extras[0]["transaction"], deps.connection.transaction_obj)
        self.assertEqual(deps.extra_repository.extras[0]["extra"]["relation_id"], "turnover_rel_1")
        self.assertEqual(deps.extra_repository.extras[0]["extra"]["note"], "facade note")
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["scope_type"], "turnover_ledger")
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["reason"], "relation_extra_update")
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["scope_keys"], ["all"])
        self.assertEqual(result["extra"]["relation_id"], "turnover_rel_1")

    def test_relation_extra_write_facade_rolls_back_extra_when_dirty_outbox_fails(self) -> None:
        # PF-P056 target contract: target semantics must not preserve current best-effort success behavior.
        uow, deps = self._build_uow(dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True))
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            facade.update_relation_extra(
                relation_id="turnover_rel_1",
                payload={"note": "must roll back"},
                actor_id="finance-user",
                tenant_id="default",
                scope_keys=["all"],
            )

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_relation_extra_write_facade_command_result_are_not_http_coupled(self) -> None:
        # PF-P056 target contract: command/result must not carry HTTP response or auth module dependencies.
        uow, _deps = self._build_uow()
        facade = self._write_facade_class()(uow=uow)

        result = facade.update_relation_extra(
            relation_id="turnover_rel_1",
            payload={"note": "service-layer payload"},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
        )

        self.assertIsInstance(result, dict)
        forbidden_keys = {"headers", "cookies", "cookie", "response", "status_code", "http_status", "auth"}
        self.assertTrue(forbidden_keys.isdisjoint(result))

    def test_relation_extra_write_facade_uses_row_provider_without_http_coupling(self) -> None:
        uow, _deps = self._build_uow()
        row_provider = _RecordingRelationExtraRowProvider()
        facade = self._write_facade_class()(uow=uow, row_provider=row_provider)

        result = facade.update_relation_extra(
            relation_id="turnover_rel_1",
            payload={"note": "row provider note"},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
        )

        self.assertEqual(
            row_provider.calls,
            [
                {
                    "relation_id": "turnover_rel_1",
                    "extra": {
                        "note": "row provider note",
                        "relation_id": "turnover_rel_1",
                        "updated_by": "finance-user",
                    },
                }
            ],
        )
        self.assertEqual(result["extra"]["note"], "row provider note")
        self.assertEqual(result["row"]["relation_id"], "turnover_rel_1")
        self.assertEqual(result["row"]["note"], "row provider note")
        forbidden_keys = {"headers", "cookies", "cookie", "response", "status_code", "http_status", "auth"}
        self.assertTrue(forbidden_keys.isdisjoint(result))

    def test_relation_extra_repository_adapter_saves_single_extra_with_supplied_transaction(self) -> None:
        module = self._write_adapters_module()
        adapter_class = getattr(module, "TurnoverLedgerExtraRepositoryAdapter")
        factory = _RecordingRepositoryFactory()
        transaction = _RecordingTransaction()
        adapter = adapter_class(repository_factory=factory)

        adapter.save_extra({"relation_id": "turnover_rel_1", "note": "adapter note"}, transaction=transaction)

        self.assertEqual(factory.transactions, [transaction])
        self.assertEqual(
            factory.repositories[0].saved_snapshots,
            [{"extras": {"turnover_rel_1": {"relation_id": "turnover_rel_1", "note": "adapter note"}}}],
        )

    def test_relation_extra_repository_adapter_rejects_application_god_object(self) -> None:
        adapter_class = getattr(self._write_adapters_module(), "TurnoverLedgerExtraRepositoryAdapter")

        with self.assertRaises(TypeError):
            adapter_class(application=object())

    def test_turnover_dirty_outbox_writer_uses_transaction_bound_queue_for_each_scope(self) -> None:
        module = self._write_adapters_module()
        writer_class = getattr(module, "TurnoverLedgerDirtyOutboxWriter")
        queue = _TransactionOnlyQueueRepository()
        transaction = _RecordingTransaction()
        writer = writer_class(queue_repository=queue, tenant_id="tenant-a", priority="high", trace_id="trace-1")

        events = writer.enqueue_refresh(
            transaction=transaction,
            scope_type="turnover_ledger",
            scope_keys=["all", "2026-05"],
            reason="relation_extra_update",
            payload={"ignored": "not part of queue primitive"},
        )

        self.assertEqual(events, queue.calls)
        self.assertEqual([call["transaction"] for call in queue.calls], [transaction, transaction])
        self.assertEqual([call["scope_key"] for call in queue.calls], ["all", "2026-05"])
        self.assertEqual([call["scope_type"] for call in queue.calls], ["turnover_ledger", "turnover_ledger"])
        self.assertEqual([call["reason"] for call in queue.calls], ["relation_extra_update", "relation_extra_update"])
        self.assertEqual([call["tenant_id"] for call in queue.calls], ["tenant-a", "tenant-a"])
        self.assertEqual([call["priority"] for call in queue.calls], ["high", "high"])
        self.assertEqual([call["trace_id"] for call in queue.calls], ["trace-1", "trace-1"])

    def test_turnover_dirty_outbox_writer_rejects_non_transactional_queue(self) -> None:
        writer_class = getattr(self._write_adapters_module(), "TurnoverLedgerDirtyOutboxWriter")
        writer = writer_class(queue_repository=_NonTransactionalQueueRepository())

        with self.assertRaisesRegex(RuntimeError, "enqueue_read_model_refresh_in_transaction"):
            writer.enqueue_refresh(
                transaction=_RecordingTransaction(),
                scope_type="turnover_ledger",
                scope_keys=["all"],
                reason="relation_extra_update",
            )
