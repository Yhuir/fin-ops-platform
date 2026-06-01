from __future__ import annotations

import importlib
import unittest
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable


"""
PF-P053 target contract tests.

These tests intentionally describe the Turnover Ledger write Unit of Work target
state. They are marked expectedFailure until the minimal TurnoverLedgerWriteUnitOfWork
skeleton exists. Keep them as explicit contracts rather than skip markers so an
unexpected success signals that the target behavior has become implemented.
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


class TurnoverLedgerUoWContractTests(unittest.TestCase):
    def _uow_class(self) -> type:
        module = importlib.import_module("fin_ops_platform.services.turnover_ledger_write_uow")
        return getattr(module, "TurnoverLedgerWriteUnitOfWork")

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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
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

    @unittest.expectedFailure
    def test_uow_constructor_requires_granular_ports_not_application_god_object(self) -> None:
        uow_class = self._uow_class()

        with self.assertRaises(TypeError):
            uow_class(application=object())

