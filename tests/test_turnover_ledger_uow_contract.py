from __future__ import annotations

import importlib
import unittest
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

from fin_ops_platform.services.workbench_idempotency import (
    InMemoryWorkbenchIdempotencyRepository,
    WorkbenchIdempotencyInProgress,
    WorkbenchIdempotencyKeyConflict,
)


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
    idempotency_key: str = ""
    request_fingerprint: str = ""


class _RecordingTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.executed: list[dict[str, object]] = []

    def record(self, operation: str, **payload: object) -> None:
        self.calls.append((operation, dict(payload)))

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append({"sql": sql, "params": params})


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

    def save_tag_selection_settings(
        self,
        *,
        next_snapshot: dict[str, object],
        audit_event: dict[str, object],
        transaction: object,
    ) -> None:
        self.saved.append(
            {
                "next_snapshot": dict(next_snapshot),
                "audit_event": dict(audit_event),
                "transaction": transaction,
            }
        )

    def append_audit(self, event: dict[str, object], *, transaction: object) -> None:
        self.audit.append({"event": dict(event), "transaction": transaction})


class _RecordingBankdetailPort:
    def __init__(self, *, result: dict[str, object] | None = None) -> None:
        self.category_updates: list[dict[str, object]] = []
        self.result = result or {"updated_categories": [{"transaction_id": "bank_txn_1"}]}

    def apply_turnover_category_updates(
        self,
        updates: list[dict[str, object]],
        *,
        transaction: object,
        actor_id: str | None = None,
    ) -> dict[str, object]:
        self.category_updates.append({"updates": list(updates), "transaction": transaction})
        if actor_id is not None:
            self.category_updates[-1]["actor_id"] = actor_id
        return dict(self.result)


class _RecordingConfirmRelationPort:
    def __init__(self, *, result: dict[str, object] | None = None) -> None:
        self.confirm_calls: list[dict[str, object]] = []
        self.result = result or {
            "relation": {
                "relation_id": "turnover_rel_1",
                "status": "confirmed",
                "bank_row_ids": ["bank_txn_1", "bank_txn_2"],
            }
        }

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        transaction: object,
    ) -> dict[str, object]:
        self.confirm_calls.append(
            {
                "bank_row_ids": list(bank_row_ids),
                "actor_id": actor_id,
                "note": note,
                "transaction": transaction,
            }
        )
        return dict(self.result)


class _RecordingWithdrawRelationPort:
    def __init__(self, *, result: dict[str, object] | None = None) -> None:
        self.withdraw_calls: list[dict[str, object]] = []
        self.result = result or {
            "relation": {
                "relation_id": "turnover_rel_1",
                "status": "withdrawn",
                "bank_row_ids": ["bank_txn_1", "bank_txn_2"],
            }
        }

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor_id: str,
        note: str | None,
        transaction: object,
    ) -> dict[str, object]:
        self.withdraw_calls.append(
            {
                "relation_id": relation_id,
                "actor_id": actor_id,
                "note": note,
                "transaction": transaction,
            }
        )
        return dict(self.result)


class _RecordingDirtyOutboxWriter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []
        self.batch_calls: list[dict[str, object]] = []

    def enqueue_refreshes(
        self,
        *,
        transaction: object,
        refreshes: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if self.fail:
            raise RuntimeError("forced dirty/outbox failure")
        self.batch_calls.append(
            {
                "transaction": transaction,
                "refreshes": [dict(refresh) for refresh in refreshes],
            }
        )
        events: list[dict[str, object]] = []
        for refresh in refreshes:
            call = {
                "transaction": transaction,
                "scope_type": str(refresh.get("scope_type") or ""),
                "scope_keys": list(refresh.get("scope_keys") or []),
                "reason": str(refresh.get("reason") or ""),
                "payload": dict(refresh.get("payload") or {}),
            }
            self.calls.append(call)
            events.append(call)
        return events


class _StalePreconditionPort:
    def __init__(self, *, stale: bool = False) -> None:
        self.stale = stale
        self.checked: list[dict[str, object]] = []

    def assert_current(self, *, expected_versions: dict[str, object], transaction: object) -> None:
        self.checked.append({"expected_versions": dict(expected_versions), "transaction": transaction})
        if self.stale:
            raise RuntimeError("turnover_write_conflict")


class _RecordingIdempotencyStore:
    def __init__(self) -> None:
        self.inner = InMemoryWorkbenchIdempotencyRepository()
        self.calls: list[dict[str, object]] = []

    def for_transaction(self, transaction: object) -> "_RecordingIdempotencyStore":
        self.calls.append({"operation": "for_transaction", "transaction": transaction})
        return self

    def get_committed_or_reserved(
        self,
        tenant_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> object:
        self.calls.append(
            {
                "operation": "get",
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
            }
        )
        return self.inner.get_committed_or_reserved(tenant_id, actor_id, idempotency_key)

    def reserve(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action_name: str,
        idempotency_key: str,
        request_fingerprint: str,
        request_payload: dict[str, Any] | None = None,
        expires_at: object | None = None,
    ) -> object:
        self.calls.append(
            {
                "operation": "reserve",
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "action_name": action_name,
                "idempotency_key": idempotency_key,
                "request_fingerprint": request_fingerprint,
                "request_payload": dict(request_payload or {}),
            }
        )
        return self.inner.reserve(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            request_payload=request_payload,
        )

    def commit(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action_name: str,
        idempotency_key: str,
        request_fingerprint: str,
        response_payload: dict[str, Any],
        source_versions: dict[str, Any] | None = None,
        outbox_event_ids: list[Any] | None = None,
    ) -> object:
        self.calls.append(
            {
                "operation": "commit",
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "action_name": action_name,
                "idempotency_key": idempotency_key,
                "request_fingerprint": request_fingerprint,
                "response_payload": dict(response_payload),
                "source_versions": dict(source_versions or {}),
                "outbox_event_ids": list(outbox_event_ids or []),
            }
        )
        return self.inner.commit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            response_payload=response_payload,
            source_versions=source_versions,
            outbox_event_ids=outbox_event_ids,
        )


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


class _RecordingSettingsRepository:
    def __init__(self) -> None:
        self.saved_settings: list[dict[str, object]] = []
        self.audit_events: list[dict[str, object]] = []

    def save_app_settings(self, payload: dict[str, object]) -> None:
        self.saved_settings.append(dict(payload))

    def append_audit(self, event: dict[str, object]) -> None:
        self.audit_events.append(dict(event))


class _RecordingSettingsRepositoryFactory:
    def __init__(self) -> None:
        self.transactions: list[object] = []
        self.repositories: list[_RecordingSettingsRepository] = []

    def __call__(self, transaction: object) -> _RecordingSettingsRepository:
        self.transactions.append(transaction)
        repository = _RecordingSettingsRepository()
        self.repositories.append(repository)
        return repository


class _RecordingBankdetailWriteRepository:
    def __init__(self) -> None:
        self.category_updates: list[dict[str, object]] = []

    def apply_turnover_category_updates(
        self,
        updates: list[dict[str, object]],
        *,
        actor_id: str,
    ) -> dict[str, object]:
        self.category_updates.append({"updates": list(updates), "actor_id": actor_id})
        return {
            "updated_categories": [
                {
                    "transaction_id": update.get("transaction_id"),
                    "category_code": update.get("category_code"),
                }
                for update in updates
            ]
        }


class _RecordingBankdetailRepositoryFactory:
    def __init__(self) -> None:
        self.transactions: list[object] = []
        self.repositories: list[_RecordingBankdetailWriteRepository] = []

    def __call__(self, transaction: object) -> _RecordingBankdetailWriteRepository:
        self.transactions.append(transaction)
        repository = _RecordingBankdetailWriteRepository()
        self.repositories.append(repository)
        return repository


class _RecordingTurnoverPersistenceRepository:
    def __init__(self) -> None:
        self.saved_relations: list[dict[str, object]] = []
        self.saved_relation_changes: list[dict[str, object]] = []
        self.saved_categories: list[dict[str, object]] = []

    def save_turnover_relations(self, snapshot: dict[str, object]) -> None:
        self.saved_relations.append(dict(snapshot))

    def save_turnover_relation_change(
        self,
        *,
        relation: dict[str, object],
        audit_event: dict[str, object],
    ) -> None:
        self.saved_relation_changes.append(
            {"relation": dict(relation), "audit_event": dict(audit_event)}
        )

    def save_bank_transaction_categories(self, snapshot: dict[str, object]) -> None:
        self.saved_categories.append(dict(snapshot))


class _RecordingTurnoverPersistenceRepositoryFactory:
    def __init__(self) -> None:
        self.transactions: list[object] = []
        self.repositories: list[_RecordingTurnoverPersistenceRepository] = []

    def __call__(self, transaction: object) -> _RecordingTurnoverPersistenceRepository:
        self.transactions.append(transaction)
        repository = _RecordingTurnoverPersistenceRepository()
        self.repositories.append(repository)
        return repository


class _RecordingTurnoverRelationService:
    def __init__(self) -> None:
        self.rebuilds: list[list[dict[str, object]]] = []
        self.refreshes: list[list[dict[str, object]]] = []
        self._audit_log: list[dict[str, object]] = []
        self._snapshot = {"relations": {"turnover_rel_1": {"status": "confirmed"}}, "audit_log": []}

    def rebuild_from_bank_rows(self, rows: list[dict[str, object]]) -> None:
        self.rebuilds.append([dict(row) for row in rows])

    def refresh_bank_rows(self, rows: list[dict[str, object]]) -> None:
        self.refreshes.append([dict(row) for row in rows])

    def preview_zero_difference_closure(
        self,
        bank_row_ids: list[str],
        *,
        actor: str,
        note: str | None,
    ) -> dict[str, object]:
        return {
            "relation_id": "turnover_rel_preview",
            "status": "confirmed",
            "bank_row_ids": list(bank_row_ids),
            "principal_amount": "100.00",
            "settled_amount": "100.00",
            "created_by": actor,
            "evidence": {"note": note},
        }

    def append_audit(self, *, relation_id: str, action: str) -> None:
        self._audit_log.append({"relation_id": relation_id, "action": action})

    def audit_log(self) -> list[dict[str, object]]:
        return [dict(event) for event in self._audit_log]

    def audit_event_cursor(self) -> int:
        return len(self._audit_log)

    def latest_audit_event(self, relation_id: str, *, after_cursor: int) -> dict[str, object] | None:
        if len(self._audit_log) <= after_cursor or self._audit_log[-1].get("relation_id") != relation_id:
            return None
        return dict(self._audit_log[-1])

    def snapshot(self) -> dict[str, object]:
        return dict(self._snapshot)


class _RecordingTurnoverRoutes:
    def __init__(self, relation_service: _RecordingTurnoverRelationService | None = None) -> None:
        self._relation_service = relation_service
        self.confirm_calls: list[dict[str, object]] = []
        self.withdraw_calls: list[dict[str, object]] = []

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor: str,
        note: str | None,
    ) -> dict[str, object]:
        self.confirm_calls.append({"bank_row_ids": list(bank_row_ids), "actor": actor, "note": note})
        if self._relation_service is not None:
            self._relation_service.append_audit(relation_id="turnover_rel_1", action="confirmed")
        return {"relation": {"relation_id": "turnover_rel_1", "status": "confirmed"}}

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor: str,
        note: str | None,
    ) -> dict[str, object]:
        self.withdraw_calls.append({"relation_id": relation_id, "actor": actor, "note": note})
        if self._relation_service is not None:
            self._relation_service.append_audit(relation_id=relation_id, action="withdrawn")
        return {"relation": {"relation_id": relation_id, "status": "withdrawn"}}


class _RecordingBankTransactionCategoryService:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []
        self._snapshot = {"categories": {"bank_txn_1": {"category_code": "borrow_in"}}, "audit_log": []}

    def apply_turnover_updates(self, updates: list[dict[str, object]], *, actor: str) -> dict[str, object]:
        self.updates.append({"updates": [dict(update) for update in updates], "actor": actor})
        return {"updated_categories": [dict(update) for update in updates]}

    def snapshot(self) -> dict[str, object]:
        return dict(self._snapshot)

    def get(self, transaction_id: str) -> dict[str, object]:
        return {"transaction_id": transaction_id, **dict(self._snapshot["categories"][transaction_id])}

    def restore_snapshot(self, snapshot: dict[str, object]) -> None:
        self._snapshot = dict(snapshot)


class _FailingTurnoverRelationPort:
    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        note: str | None,
        transaction: object,
    ) -> dict[str, object]:
        raise RuntimeError("relation adapter unavailable")


class _TransactionOnlyQueueRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.batch_calls: list[dict[str, object]] = []

    def enqueue_read_model_refreshes_in_transaction(
        self,
        *,
        transaction: object,
        refreshes: list[dict[str, object]],
        tenant_id: str,
        priority: str,
        trace_id: str | None,
    ) -> list[dict[str, object]]:
        self.batch_calls.append(
            {
                "transaction": transaction,
                "refreshes": [dict(refresh) for refresh in refreshes],
                "tenant_id": tenant_id,
                "priority": priority,
                "trace_id": trace_id,
            }
        )
        events = [
            {
                "transaction": transaction,
                "scope_type": str(refresh.get("scope_type") or ""),
                "scope_key": str(refresh.get("scope_key") or ""),
                "reason": str(refresh.get("reason") or ""),
                "tenant_id": tenant_id,
                "priority": priority,
                "trace_id": trace_id,
                "metadata": dict(refresh.get("metadata") or {}),
            }
            for refresh in refreshes
        ]
        self.calls.extend(events)
        return events

    def enqueue_read_model_refresh(self, **_kwargs: object) -> None:
        raise AssertionError("non-transaction enqueue must not be used")


class _NonTransactionalQueueRepository:
    def enqueue_read_model_refresh(self, **_kwargs: object) -> None:
        return None


class _AppSettingsStateStore:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = dict(payload)
        self.saved_payloads: list[dict[str, object]] = []

    def load_app_settings(self) -> dict[str, object]:
        return dict(self.payload)

    def save_app_settings(self, payload: dict[str, object]) -> None:
        self.payload = dict(payload)
        self.saved_payloads.append(dict(payload))


class _ProjectCostingStub:
    def restore_manual_projects(self, _projects: list[object]) -> None:
        return None

    def list_projects(self) -> list[object]:
        return []


def _tag_selection_settings_payload() -> dict[str, object]:
    return {
        "bank_transaction_tags": {
            "version": 1,
            "definitions": [
                {
                    "code": "external_rule_borrow_out",
                    "label": "借出款",
                    "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                    "source": "custom",
                    "status": "active",
                    "output_primary_label": "外部往来款付款",
                    "output_sub_label": "借出款",
                    "turnover_role": "external_turnover",
                    "turnover_action_type": "pending_collection",
                    "direction": "any",
                    "account_scope": {"type": "any", "values": []},
                    "rules": {
                        "match_fields": ["all_text"],
                        "contains_any": ["借出"],
                        "contains_all": [],
                        "exact_any": [],
                        "regex_any": [],
                        "none_of": [],
                    },
                },
                {
                    "code": "external_rule_repaid",
                    "label": "归还借款",
                    "path": ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
                    "source": "custom",
                    "status": "active",
                    "output_primary_label": "外部往来款付款",
                    "output_sub_label": "归还借款",
                    "turnover_role": "external_turnover",
                    "turnover_action_type": "repaid",
                    "direction": "any",
                    "account_scope": {"type": "any", "values": []},
                    "rules": {
                        "match_fields": ["all_text"],
                        "contains_any": ["归还"],
                        "contains_all": [],
                        "exact_any": [],
                        "regex_any": [],
                        "none_of": [],
                    },
                },
            ],
        },
        "turnover_ledger_tag_selection": {
            "version": 1,
            "selected_tag_codes": ["external_rule_borrow_out", "external_rule_repaid"],
        },
    }


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


class _RecordingRelationExtraNormalizer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def __call__(self, *, relation_id: str, payload: dict[str, object], actor_id: str) -> dict[str, object]:
        self.calls.append({"relation_id": relation_id, "payload": dict(payload), "actor_id": actor_id})
        if self.fail:
            raise ValueError("invalid normalized extra")
        return {
            "relation_id": relation_id,
            "interest_rate_type": str(payload.get("interest_rate_type") or "none"),
            "interest_rate_value": "0.000000",
            "interest_paid_amount": "0.00",
            "interest_paid_date": None,
            "interest_payment_method": "",
            "note": f"normalized:{payload.get('note', '')}",
            "updated_at": "2026-06-02T00:00:00+00:00",
            "updated_by": actor_id,
        }


class _RecordingTagSelectionNormalizer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def __call__(self, *, payload: dict[str, object], actor_id: str) -> dict[str, object]:
        self.calls.append({"payload": dict(payload), "actor_id": actor_id})
        if self.fail:
            raise ValueError("invalid tag selection")
        return {
            "next_snapshot": {
                "turnover_ledger_tag_selection": {
                    "version": 2,
                    "selected_tag_codes": ["external_rule_borrow_out"],
                }
            },
            "next_selection": {
                "version": 2,
                "selected_tag_codes": ["external_rule_borrow_out"],
            },
            "audit_event": {
                "actor_id": actor_id,
                "old_version": 1,
                "new_version": 2,
            },
            "public_payload": {
                "version": 2,
                "selected_tag_codes": ["external_rule_borrow_out"],
                "active_tags": [{"code": "external_rule_borrow_out", "label": "借出款"}],
            },
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

    def _extra_service_class(self) -> type:
        module = importlib.import_module("fin_ops_platform.services.turnover_ledger_extra_service")
        return getattr(module, "TurnoverLedgerExtraService")

    def test_cost_statistics_relation_delta_requires_concrete_affected_month(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.turnover_ledger_write_facade")

        self.assertEqual(module._active_cost_statistics_scope_keys([]), [])
        self.assertEqual(module._active_cost_statistics_scope_keys(["all"]), [])
        self.assertEqual(
            module._active_cost_statistics_scope_keys(["2026-02", "2026-02"]),
            ["active:2026-02"],
        )

    def test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service(self) -> None:
        module = self._write_adapters_module()
        bank_row_reads: list[list[str]] = []
        rules_reads: list[None] = []

        def bank_rows_by_ids(row_ids: list[str]) -> list[dict[str, object]]:
            bank_row_reads.append(list(row_ids))
            return [
                {"id": "bank_txn_1", "effective_category_code": "requires-oa"},
                {"id": "bank_txn_2", "category_code": "requires-invoice"},
                {"id": "bank_txn_3", "effective_category_code": "requires-oa"},
            ]

        def rules_payload() -> dict[str, object]:
            rules_reads.append(None)
            return {
                "version": 7,
                "requirements_by_tag_code": {
                    "requires-oa": {"requires_oa": True, "requires_invoice": False},
                    "requires-invoice": {"requires_oa": False, "requires_invoice": True},
                },
            }

        class RecordingRelationCommandService:
            def __init__(self) -> None:
                self.prepare_calls: list[dict[str, object]] = []
                self.confirm_calls: list[dict[str, object]] = []

            def prepare_confirm_relation(self, **kwargs: object) -> object:
                self.prepare_calls.append(dict(kwargs))
                return SimpleNamespace(active_relations=[])

            def confirm_relation(self, **kwargs: object) -> dict[str, object]:
                self.confirm_calls.append(dict(kwargs))
                return {
                    "relation": {
                        "case_id": str(kwargs["case_id"]),
                        "row_ids": list(kwargs["row_ids"]),
                        "row_types": list(kwargs["row_types"]),
                        "relation_mode": str(kwargs["relation_mode"]),
                        "status": "active",
                        "month_scope": str(kwargs.get("month_scope") or "all"),
                        "special_metadata": dict(kwargs.get("special_metadata") or {}),
                    }
                }

        command = RecordingRelationCommandService()
        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: command,
            bank_rows_by_ids_provider=bank_rows_by_ids,
            rules_payload_provider=rules_payload,
        )
        preparation = port.prepare_turnover_manual_closure_write(
            bank_row_ids=["bank_txn_1", "bank_txn_2", "bank_txn_3"],
            affected_months=["2026-02"],
            transaction=object(),
        )

        relation = port.create_turnover_manual_closure(
            closure={
                "relation_id": "turnover_rel_closure",
                "principal_amount": "100.00",
                "settled_amount": "100.00",
                "evidence": {"closure_mode": "manual_zero_difference_group"},
            },
            bank_row_ids=["bank_txn_1", "bank_txn_2", "bank_txn_3"],
            actor_id="finance-user",
            note="manual closure",
            affected_months=["2026-02"],
            transaction=object(),
            preparation=preparation,
        )

        self.assertEqual(relation["case_id"], "turnover:turnover_rel_closure")
        self.assertEqual(len(command.confirm_calls), 1)
        call = command.confirm_calls[0]
        self.assertEqual(call["case_id"], "turnover:turnover_rel_closure")
        self.assertEqual(call["row_ids"], ["bank_txn_1", "bank_txn_2", "bank_txn_3"])
        self.assertEqual(call["row_types"], ["bank", "bank", "bank"])
        self.assertEqual(call["relation_mode"], "turnover_manual_closure")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["month_scope"], "2026-02")
        self.assertEqual(call["special_metadata"]["source"], "turnover_ledger")
        self.assertNotIn("turnover_relation_id", call["special_metadata"])
        self.assertNotIn("turnover_relation_id", call["evidence"])
        self.assertEqual(call["special_metadata"]["turnover_closure_mode"], "manual_zero_difference_group")
        self.assertEqual(call["special_metadata"]["turnover_closure_affected_months"], ["2026-02"])
        self.assertTrue(call["special_metadata"]["requires_oa"])
        self.assertTrue(call["special_metadata"]["requires_invoice"])
        self.assertEqual(
            call["special_metadata"]["paired_requirement_source"],
            "bank_transaction_paired_policy",
        )
        self.assertEqual(
            call["special_metadata"]["paired_requirement_tag_codes"],
            ["requires-oa", "requires-invoice"],
        )
        self.assertEqual(call["special_metadata"]["paired_requirement_version"], 7)
        self.assertEqual(bank_row_reads, [["bank_txn_1", "bank_txn_2", "bank_txn_3"]])
        self.assertEqual(len(rules_reads), 1)
        self.assertEqual(call["history_operation_type"], "turnover_manual_closure_confirm")
        self.assertIs(call["preparation"], preparation.confirm_preparation)

    def test_turnover_workbench_pair_port_fails_closed_on_one_missing_bank_tag(self) -> None:
        module = self._write_adapters_module()
        bank_row_reads: list[list[str]] = []
        rules_reads: list[None] = []
        confirm_calls: list[dict[str, object]] = []

        def prepare_confirm_relation(**_kwargs: object) -> object:
            return SimpleNamespace(active_relations=[])

        def confirm_relation(**kwargs: object) -> dict[str, object]:
            confirm_calls.append(dict(kwargs))
            return {"relation": {"case_id": kwargs["case_id"]}}

        command = SimpleNamespace(
            prepare_confirm_relation=prepare_confirm_relation,
            confirm_relation=confirm_relation,
        )

        def bank_rows_by_ids(row_ids: list[str]) -> list[dict[str, object]]:
            bank_row_reads.append(list(row_ids))
            return [
                {"id": "bank-known", "effective_category_code": "requires-neither"},
                {"id": "bank-missing", "effective_category_code": ""},
            ]

        def rules_payload() -> dict[str, object]:
            rules_reads.append(None)
            return {
                "version": 8,
                "requirements_by_tag_code": {
                    "requires-neither": {"requires_oa": False, "requires_invoice": False}
                },
            }

        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda _transaction: command,
            bank_rows_by_ids_provider=bank_rows_by_ids,
            rules_payload_provider=rules_payload,
        )
        preparation = port.prepare_turnover_manual_closure_write(
            bank_row_ids=["bank-known", "bank-missing"],
            affected_months=["2026-02"],
            transaction=object(),
        )
        port.create_turnover_manual_closure(
            closure={
                "relation_id": "turnover-partial-missing-tag",
                "principal_amount": "100.00",
                "settled_amount": "100.00",
            },
            bank_row_ids=["bank-known", "bank-missing"],
            actor_id="finance-user",
            note=None,
            affected_months=["2026-02"],
            transaction=object(),
            preparation=preparation,
        )

        metadata = dict(confirm_calls[0]["special_metadata"])
        self.assertEqual(metadata["paired_requirement_tag_codes"], ["requires-neither"])
        self.assertTrue(metadata["requires_oa"])
        self.assertTrue(metadata["requires_invoice"])
        self.assertEqual(bank_row_reads, [["bank-known", "bank-missing"]])
        self.assertEqual(rules_reads, [None])

    def test_turnover_manual_closure_preparation_keeps_cross_month_scope_keys(self) -> None:
        module = self._write_adapters_module()

        class RecordingRelationCommandService:
            def __init__(self) -> None:
                self.prepare_calls: list[dict[str, object]] = []

            def prepare_confirm_relation(self, **kwargs: object) -> object:
                self.prepare_calls.append(dict(kwargs))
                return SimpleNamespace(active_relations=[])

        command = RecordingRelationCommandService()
        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: command,
        )

        preparation = port.prepare_turnover_manual_closure_write(
            bank_row_ids=["bank-april", "bank-june"],
            affected_months=["2026-04", "2026-06"],
            transaction=object(),
        )

        self.assertEqual(len(command.prepare_calls), 1)
        self.assertEqual(command.prepare_calls[0]["row_ids"], ["bank-april", "bank-june"])
        self.assertEqual(command.prepare_calls[0]["row_types"], ["bank", "bank"])
        self.assertEqual(command.prepare_calls[0]["month_scope"], "all")
        self.assertEqual(command.prepare_calls[0]["scope_keys_hint"], ["2026-04", "2026-06"])
        self.assertEqual(preparation.bank_row_ids, ("bank-april", "bank-june"))

    def test_turnover_manual_closure_merges_existing_oa_bank_relations(self) -> None:
        module = self._write_adapters_module()
        bank_row_reads: list[list[str]] = []
        rules_reads: list[None] = []

        def bank_rows_by_ids(row_ids: list[str]) -> list[dict[str, object]]:
            bank_row_reads.append(list(row_ids))
            return [
                {"id": row_id, "effective_category_code": "external-turnover"}
                for row_id in row_ids
            ]

        def rules_payload() -> dict[str, object]:
            rules_reads.append(None)
            return {
                "version": 5,
                "requirements_by_tag_code": {
                    "external-turnover": {"requires_oa": True, "requires_invoice": False}
                },
            }

        class RecordingRelationCommandService:
            def __init__(self) -> None:
                self.prepare_calls: list[dict[str, object]] = []
                self.confirm_calls: list[dict[str, object]] = []

            def prepare_confirm_relation(self, **kwargs: object) -> object:
                self.prepare_calls.append(dict(kwargs))
                return SimpleNamespace(active_relations=[
                    {
                        "case_id": "case-oa-1",
                        "row_ids": ["oa-1", "bank-1"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-02",
                    },
                    {
                        "case_id": "case-oa-2",
                        "row_ids": ["oa-2", "bank-2"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-02",
                    },
                ])

            def confirm_relation(self, **kwargs: object) -> dict[str, object]:
                self.confirm_calls.append(dict(kwargs))
                return {
                    "relation": {
                        "case_id": str(kwargs["case_id"]),
                        "row_ids": list(kwargs["row_ids"]),
                        "row_types": list(kwargs["row_types"]),
                        "relation_mode": str(kwargs["relation_mode"]),
                        "status": "active",
                        "month_scope": str(kwargs.get("month_scope") or "all"),
                        "special_metadata": dict(kwargs.get("special_metadata") or {}),
                    }
                }

        command = RecordingRelationCommandService()
        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: command,
            bank_rows_by_ids_provider=bank_rows_by_ids,
            rules_payload_provider=rules_payload,
        )
        preparation = port.prepare_turnover_manual_closure_write(
            bank_row_ids=["bank-1", "bank-2", "bank-3"],
            affected_months=["2026-02"],
            transaction=object(),
        )

        relation = port.create_turnover_manual_closure(
            closure={
                "relation_id": "turnover_rel_closure",
                "principal_amount": "100.00",
                "settled_amount": "100.00",
                "evidence": {"closure_mode": "manual_zero_difference_group"},
            },
            bank_row_ids=["bank-1", "bank-2", "bank-3"],
            actor_id="finance-user",
            note="manual closure",
            affected_months=["2026-02"],
            transaction=object(),
            preparation=preparation,
        )

        self.assertEqual(relation["case_id"], "turnover:turnover_rel_closure")
        self.assertEqual(len(command.prepare_calls), 1)
        self.assertEqual(len(command.confirm_calls), 1)
        call = command.confirm_calls[0]
        self.assertEqual(call["case_id"], "turnover:turnover_rel_closure")
        self.assertEqual(call["row_ids"], ["oa-1", "bank-1", "oa-2", "bank-2", "bank-3"])
        self.assertEqual(call["row_types"], ["oa", "bank", "oa", "bank", "bank"])
        self.assertEqual(call["relation_mode"], "turnover_manual_closure")
        self.assertTrue(call["replace_existing"])
        self.assertEqual(
            [item["case_id"] for item in list(call["before_relations"] or [])],
            ["case-oa-1", "case-oa-2"],
        )
        self.assertEqual(
            call["special_metadata"]["turnover_closure_bank_row_ids"],
            ["bank-1", "bank-2", "bank-3"],
        )
        self.assertEqual(
            call["special_metadata"]["paired_requirement_tag_codes"],
            ["external-turnover"],
        )
        self.assertEqual(bank_row_reads, [["bank-1", "bank-2", "bank-3"]])
        self.assertEqual(len(rules_reads), 1)

    def test_turnover_manual_closure_rejects_unselected_bank_member_without_second_bank_read(self) -> None:
        module = self._write_adapters_module()
        raw_bank_reads: list[list[str]] = []
        rules_reads: list[None] = []

        def load_rows(row_ids: list[str]) -> list[dict[str, object]]:
            raw_bank_reads.append(list(row_ids))
            return [
                {"id": row_id, "effective_category_code": "external-turnover"}
                for row_id in row_ids
            ]

        selection_port = module.TurnoverLedgerBankRowSelectionPort(
            bank_rows_by_ids_provider=load_rows
        )
        selection_port.rows_by_ids(["bank-1", "bank-2"])

        class ExistingRelationCommandService:
            def __init__(self) -> None:
                self.confirm_calls: list[dict[str, object]] = []

            def prepare_confirm_relation(self, **_kwargs: object) -> object:
                return SimpleNamespace(active_relations=[
                    {
                        "case_id": "case-oa-with-extra-bank",
                        "row_ids": ["oa-1", "bank-1", "bank-unselected"],
                        "row_types": ["oa", "bank", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                    }
                ])

            def confirm_relation(self, **kwargs: object) -> dict[str, object]:
                self.confirm_calls.append(dict(kwargs))
                raise AssertionError("unselected bank member must block before relation/history mutation")

        command = ExistingRelationCommandService()
        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: command,
            bank_rows_by_ids_provider=selection_port.rows_by_ids,
            rules_payload_provider=lambda: rules_reads.append(None) or {
                "version": 3,
                "requirements_by_tag_code": {
                    "external-turnover": {"requires_oa": True, "requires_invoice": False}
                },
            },
        )
        preparation = port.prepare_turnover_manual_closure_write(
            bank_row_ids=["bank-1", "bank-2"],
            affected_months=["2026-02"],
            transaction=object(),
        )

        with self.assertRaises(module.TurnoverLedgerWritePreconditionError) as context:
            port.create_turnover_manual_closure(
                closure={
                    "relation_id": "turnover_rel_closure",
                    "principal_amount": "100.00",
                    "settled_amount": "100.00",
                },
                bank_row_ids=["bank-1", "bank-2"],
                actor_id="finance-user",
                note="manual closure",
                affected_months=["2026-02"],
                transaction=object(),
                preparation=preparation,
            )

        self.assertEqual(context.exception.error_code, "turnover_relation_conflict")
        self.assertEqual(command.confirm_calls, [])
        self.assertEqual(raw_bank_reads, [["bank-1", "bank-2"]])
        self.assertEqual(rules_reads, [])

    def test_turnover_manual_closure_requirement_inputs_fail_closed_before_command(self) -> None:
        module = self._write_adapters_module()

        class RecordingRelationCommandService:
            def __init__(self) -> None:
                self.confirm_calls: list[dict[str, object]] = []

            def prepare_confirm_relation(self, **_kwargs: object) -> object:
                return SimpleNamespace(active_relations=[])

            def confirm_relation(self, **kwargs: object) -> dict[str, object]:
                self.confirm_calls.append(dict(kwargs))
                return {"relation": dict(kwargs)}

        cases = [
            (
                "missing-row",
                lambda _row_ids: [{"id": "bank-1", "effective_category_code": "external-turnover"}],
                lambda: {"version": 1, "requirements_by_tag_code": {}},
            ),
            (
                "duplicate-row",
                lambda _row_ids: [
                    {"id": "bank-1", "effective_category_code": "external-turnover"},
                    {"id": "bank-1", "effective_category_code": "external-turnover"},
                ],
                lambda: {"version": 1, "requirements_by_tag_code": {}},
            ),
            (
                "invalid-rules",
                lambda row_ids: [
                    {"id": row_id, "effective_category_code": "external-turnover"}
                    for row_id in row_ids
                ],
                lambda: [],
            ),
        ]
        for name, row_provider, rules_provider in cases:
            with self.subTest(name=name):
                command = RecordingRelationCommandService()
                port = module.TurnoverLedgerWorkbenchPairPort(
                    relation_command_service_factory=lambda transaction: command,
                    bank_rows_by_ids_provider=row_provider,
                    rules_payload_provider=rules_provider,
                )
                preparation = port.prepare_turnover_manual_closure_write(
                    bank_row_ids=["bank-1", "bank-2"],
                    affected_months=["2026-02"],
                    transaction=object(),
                )

                with self.assertRaises(module.TurnoverLedgerWritePreconditionError) as context:
                    port.create_turnover_manual_closure(
                        closure={
                            "relation_id": f"turnover-rel-{name}",
                            "principal_amount": "100.00",
                            "settled_amount": "100.00",
                        },
                        bank_row_ids=["bank-1", "bank-2"],
                        actor_id="finance-user",
                        note=None,
                        affected_months=["2026-02"],
                        transaction=object(),
                        preparation=preparation,
                    )

                self.assertEqual(context.exception.error_code, "turnover_relation_conflict")
                self.assertEqual(command.confirm_calls, [])

    def test_turnover_manual_closure_rejects_rows_already_in_turnover_closure(self) -> None:
        module = self._write_adapters_module()

        class ExistingClosureRelationCommandService:
            def prepare_confirm_relation(self, **_kwargs: object) -> object:
                return SimpleNamespace(active_relations=[
                    {
                        "case_id": "turnover:existing_closure",
                        "row_ids": ["bank-1", "bank-2"],
                        "row_types": ["bank", "bank"],
                        "status": "active",
                        "relation_mode": "turnover_manual_closure",
                    }
                ])

            def confirm_relation(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("existing turnover closure must block confirm before writing.")

        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: ExistingClosureRelationCommandService(),
        )
        preparation = port.prepare_turnover_manual_closure_write(
            bank_row_ids=["bank-1", "bank-2", "bank-3"],
            affected_months=["2026-02"],
            transaction=object(),
        )

        with self.assertRaises(module.TurnoverLedgerWritePreconditionError) as context:
            port.create_turnover_manual_closure(
                closure={
                    "relation_id": "turnover_rel_closure",
                    "principal_amount": "100.00",
                    "settled_amount": "100.00",
                    "evidence": {"closure_mode": "manual_zero_difference_group"},
                },
                bank_row_ids=["bank-1", "bank-2", "bank-3"],
                actor_id="finance-user",
                note="manual closure",
                affected_months=["2026-02"],
                transaction=object(),
                preparation=preparation,
            )

        self.assertEqual(context.exception.error_code, "turnover_relation_conflict")
        self.assertIn("先撤回原闭环", str(context.exception))

    def test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure(self) -> None:
        module = self._write_adapters_module()

        port = module.TurnoverLedgerWorkbenchPairPort()

        with self.assertRaises(module.TurnoverLedgerWritePreconditionError) as context:
            port.prepare_turnover_manual_closure_write(
                bank_row_ids=["bank_txn_1", "bank_txn_2"],
                affected_months=["2026-02"],
                transaction=object(),
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_command_unavailable")

    def test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service(self) -> None:
        module = self._write_adapters_module()

        class FreshRelationFacade:
            def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
                return {
                    "status": "fresh",
                    "rows": [
                        {"row_id": str(row_id), "row_type": "bank_transaction", "group_ids": ["turnover:turnover_rel_1"]}
                        for row_id in row_ids
                    ],
                    "groups": [
                        {
                            "group_id": "turnover:turnover_rel_1",
                            "payload": {
                                "group_id": "turnover:turnover_rel_1",
                                "relation_mode": "turnover_manual_closure",
                                "row_ids": list(row_ids),
                                "row_types": ["bank" for _row_id in row_ids],
                            },
                        }
                    ],
                    "read_model_scope_keys": ["2026-02"],
                }

        class RecordingRelationCommandService:
            def __init__(self) -> None:
                self.withdraw_calls: list[dict[str, object]] = []

            def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
                self.withdraw_calls.append(dict(kwargs))
                return {
                    "relation": {
                        "case_id": str(kwargs["case_id"]),
                        "status": "cancelled",
                    }
                }

        command = RecordingRelationCommandService()
        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: command,
            relation_facade=FreshRelationFacade(),
        )

        relation = port.withdraw_turnover_manual_closure(
            relation={
                "relation_id": "turnover_rel_1",
                "status": "withdrawn",
                "bank_row_ids": ["bank_txn_1", "bank_txn_2"],
            },
            actor_id="finance-user",
            note="withdraw closure",
            transaction=object(),
        )

        self.assertEqual(relation["case_id"], "turnover:turnover_rel_1")
        self.assertEqual(relation["status"], "cancelled")
        self.assertEqual(len(command.withdraw_calls), 1)
        call = command.withdraw_calls[0]
        self.assertEqual(call["case_id"], "turnover:turnover_rel_1")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["reason"], "withdraw closure")
        self.assertEqual(call["history_operation_type"], "turnover_manual_closure_withdraw")

    def test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations(self) -> None:
        module = self._write_adapters_module()

        class FreshRelationFacade:
            def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
                return {
                    "status": "fresh",
                    "rows": [
                        {"row_id": str(row_id), "row_type": "bank_transaction", "group_ids": ["turnover:turnover_rel_1"]}
                        for row_id in row_ids
                    ],
                    "groups": [
                        {
                            "group_id": "turnover:turnover_rel_1",
                            "payload": {
                                "group_id": "turnover:turnover_rel_1",
                                "relation_mode": "turnover_manual_closure",
                                "row_ids": ["oa-1", "bank-1", "oa-2", "bank-2", "bank-3"],
                                "row_types": ["oa", "bank", "oa", "bank", "bank"],
                            },
                        }
                    ],
                    "read_model_scope_keys": ["2026-02"],
                }

        class RecordingRelationCommandService:
            def __init__(self) -> None:
                self.withdraw_calls: list[dict[str, object]] = []

            def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
                self.withdraw_calls.append(dict(kwargs))
                return {
                    "relation": {
                        "case_id": str(kwargs["case_id"]),
                        "status": "cancelled",
                    },
                    "restored_relations": [
                        {"case_id": "case-oa-1", "row_ids": ["oa-1", "bank-1"], "status": "active"},
                        {"case_id": "case-oa-2", "row_ids": ["oa-2", "bank-2"], "status": "active"},
                    ],
                }

        command = RecordingRelationCommandService()
        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: command,
            relation_facade=FreshRelationFacade(),
        )

        relation = port.withdraw_turnover_manual_closure(
            relation={
                "relation_id": "turnover_rel_1",
                "status": "withdrawn",
                "bank_row_ids": ["bank-1", "bank-2", "bank-3"],
            },
            actor_id="finance-user",
            note="withdraw closure",
            transaction=object(),
        )

        self.assertEqual(relation["case_id"], "turnover:turnover_rel_1")
        self.assertEqual(relation["status"], "cancelled")
        self.assertEqual(relation["restored_relations"][0]["case_id"], "case-oa-1")
        self.assertEqual(relation["restored_relations"][1]["case_id"], "case-oa-2")
        self.assertEqual(len(command.withdraw_calls), 1)
        call = command.withdraw_calls[0]
        self.assertEqual(call["case_id"], "turnover:turnover_rel_1")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["reason"], "withdraw closure")
        self.assertEqual(call["history_operation_type"], "turnover_manual_closure_withdraw")

    def test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw(self) -> None:
        module = self._write_adapters_module()

        class FreshRelationFacade:
            def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
                return {
                    "status": "fresh",
                    "rows": [
                        {"row_id": str(row_id), "row_type": "bank_transaction", "group_ids": ["turnover:turnover_rel_1"]}
                        for row_id in row_ids
                    ],
                    "groups": [
                        {
                            "group_id": "turnover:turnover_rel_1",
                            "payload": {
                                "group_id": "turnover:turnover_rel_1",
                                "relation_mode": "turnover_manual_closure",
                                "row_ids": list(row_ids),
                                "row_types": ["bank" for _row_id in row_ids],
                            },
                        }
                    ],
                    "read_model_scope_keys": ["2026-02"],
                }

        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_facade=FreshRelationFacade(),
        )

        with self.assertRaises(module.TurnoverLedgerWritePreconditionError) as context:
            port.withdraw_turnover_manual_closure(
                relation={
                    "relation_id": "turnover_rel_1",
                    "status": "withdrawn",
                    "bank_row_ids": ["bank_txn_1", "bank_txn_2"],
                },
                actor_id="finance-user",
                note="withdraw closure",
                transaction=object(),
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_command_unavailable")

    def test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service(self) -> None:
        module = self._write_adapters_module()

        class RecordingRelationCommandService:
            def __init__(self) -> None:
                self.prepare_calls: list[dict[str, object]] = []
                self.withdraw_calls: list[dict[str, object]] = []

            def prepare_withdraw_relation(self, **kwargs: object) -> object:
                self.prepare_calls.append(dict(kwargs))
                return SimpleNamespace(
                    before_relation={
                        "case_id": str(kwargs["case_id"]),
                        "row_ids": ["bank-income-1", "bank-expense-1"],
                        "row_types": ["bank", "bank"],
                    }
                )

            def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
                self.withdraw_calls.append(dict(kwargs))
                return {
                    "relation": {
                        "case_id": str(kwargs["case_id"]),
                        "status": "cancelled",
                    },
                    "affected_months": ["2026-02"],
                    "affected_row_ids": ["bank-income-1", "bank-expense-1"],
                    "restored_relations": [
                        {"case_id": "case-oa-restore", "row_ids": ["oa-1", "bank-income-1"]},
                    ],
                }

        command = RecordingRelationCommandService()
        port = module.TurnoverLedgerWorkbenchPairPort(
            relation_command_service_factory=lambda transaction: command,
        )

        relation = port.withdraw_cash_closure_case(
            case_id="case-workbench-cash-1",
            actor_id="finance-user",
            note="withdraw cash closure",
            transaction=object(),
        )

        self.assertEqual(relation["case_id"], "case-workbench-cash-1")
        self.assertEqual(relation["status"], "cancelled")
        self.assertEqual(relation["affected_months"], ["2026-02"])
        self.assertEqual(relation["affected_row_ids"], ["bank-income-1", "bank-expense-1"])
        self.assertEqual(relation["restored_relations"][0]["case_id"], "case-oa-restore")
        self.assertEqual(command.prepare_calls, [{"case_id": "case-workbench-cash-1"}])
        self.assertEqual(len(command.withdraw_calls), 1)
        call = command.withdraw_calls[0]
        self.assertEqual(call["case_id"], "case-workbench-cash-1")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["reason"], "withdraw cash closure")
        self.assertEqual(call["history_operation_type"], "turnover_cash_closure_withdraw")
        self.assertIsNotNone(call["preparation"])

    def test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw(self) -> None:
        module = self._write_adapters_module()

        port = module.TurnoverLedgerWorkbenchPairPort()

        with self.assertRaises(module.TurnoverLedgerWritePreconditionError) as context:
            port.withdraw_cash_closure_case(
                case_id="case-workbench-cash-1",
                actor_id="finance-user",
                note="withdraw cash closure",
                transaction=object(),
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_command_unavailable")

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
        idempotency_store: _RecordingIdempotencyStore | None = None,
    ) -> tuple[object, SimpleNamespace]:
        dependencies = SimpleNamespace(
            connection=connection or _RecordingConnection(),
            relation_repository=relation_repository or _RecordingRelationRepository(),
            extra_repository=extra_repository or _RecordingExtraRepository(),
            settings_port=settings_port or _RecordingSettingsPort(),
            bankdetail_port=bankdetail_port or _RecordingBankdetailPort(),
            dirty_outbox_writer=dirty_outbox_writer or _RecordingDirtyOutboxWriter(),
            stale_precondition_port=stale_precondition_port or _StalePreconditionPort(),
            idempotency_store=idempotency_store,
        )
        kwargs = {
            "connection": dependencies.connection,
            "relation_repository": dependencies.relation_repository,
            "extra_repository": dependencies.extra_repository,
            "settings_port": dependencies.settings_port,
            "bankdetail_port": dependencies.bankdetail_port,
            "dirty_outbox_writer": dependencies.dirty_outbox_writer,
            "stale_precondition_port": dependencies.stale_precondition_port,
        }
        if idempotency_store is not None:
            kwargs["idempotency_store"] = idempotency_store
        uow = self._uow_class()(
            **kwargs,
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

    def test_relation_extra_idempotency_reserves_before_handler_and_commits_response(self) -> None:
        idempotency_store = _RecordingIdempotencyStore()
        uow, deps = self._build_uow(idempotency_store=idempotency_store)
        handler_calls: list[str] = []

        def handler(context: object) -> dict[str, object]:
            handler_calls.append("handler")
            transaction = getattr(context, "transaction")
            deps.extra_repository.save_extra({"relation_id": "turnover_rel_1"}, transaction=transaction)
            return {"extra": {"relation_id": "turnover_rel_1"}}

        result = self._run_uow(
            uow,
            _Command(
                action_name="turnover_relation_extra_update",
                scope_keys=["all"],
                payload={"relation_id": "turnover_rel_1", "extra": {"note": "idem"}},
                idempotency_key="relation-extra-idem-1",
                request_fingerprint="fingerprint-1",
            ),
            handler,
        )

        self.assertEqual(result["extra"], {"relation_id": "turnover_rel_1"})
        self.assertEqual(handler_calls, ["handler"])
        self.assertEqual([call["operation"] for call in idempotency_store.calls], ["for_transaction", "reserve", "commit"])
        self.assertEqual(deps.connection.commits, 1)
        self.assertEqual(deps.connection.rollbacks, 0)
        self.assertEqual(len(deps.extra_repository.extras), 1)
        self.assertEqual(len(deps.dirty_outbox_writer.calls), 1)

    def test_relation_extra_idempotency_replays_committed_without_handler_or_dirty_outbox(self) -> None:
        idempotency_store = _RecordingIdempotencyStore()
        uow, deps = self._build_uow(idempotency_store=idempotency_store)
        command = _Command(
            action_name="turnover_relation_extra_update",
            scope_keys=["all"],
            expected_versions={"relation:turnover_rel_1": 1},
            payload={"relation_id": "turnover_rel_1", "extra": {"note": "idem"}},
            idempotency_key="relation-extra-idem-1",
            request_fingerprint="fingerprint-1",
        )
        handler_calls = 0

        def handler(context: object) -> dict[str, object]:
            nonlocal handler_calls
            handler_calls += 1
            transaction = getattr(context, "transaction")
            deps.extra_repository.save_extra({"relation_id": "turnover_rel_1"}, transaction=transaction)
            return {"extra": {"relation_id": "turnover_rel_1"}}

        first = self._run_uow(uow, command, handler)
        deps.stale_precondition_port.stale = True
        second = self._run_uow(
            uow,
            command,
            lambda _context: self.fail("committed idempotency replay must not call handler"),
        )

        self.assertEqual(first, second)
        self.assertEqual(handler_calls, 1)
        self.assertEqual(len(deps.extra_repository.extras), 1)
        self.assertEqual(len(deps.dirty_outbox_writer.calls), 1)
        self.assertEqual(len(deps.stale_precondition_port.checked), 1)
        self.assertEqual(deps.connection.opened, 2)

    def test_relation_extra_idempotency_conflict_rejects_before_handler_or_dirty_outbox(self) -> None:
        idempotency_store = _RecordingIdempotencyStore()
        uow, deps = self._build_uow(idempotency_store=idempotency_store)
        first_command = _Command(
            action_name="turnover_relation_extra_update",
            scope_keys=["all"],
            payload={"relation_id": "turnover_rel_1", "extra": {"note": "first"}},
            idempotency_key="relation-extra-idem-conflict",
            request_fingerprint="fingerprint-1",
        )
        conflicting_command = _Command(
            action_name="turnover_relation_extra_update",
            scope_keys=["all"],
            payload={"relation_id": "turnover_rel_1", "extra": {"note": "different"}},
            idempotency_key="relation-extra-idem-conflict",
            request_fingerprint="fingerprint-2",
        )

        self._run_uow(uow, first_command, lambda _context: {"extra": {"relation_id": "turnover_rel_1"}})

        with self.assertRaises(WorkbenchIdempotencyKeyConflict):
            self._run_uow(
                uow,
                conflicting_command,
                lambda _context: self.fail("fingerprint conflict must not call handler"),
            )

        self.assertEqual(len(deps.dirty_outbox_writer.calls), 1)
        self.assertEqual(deps.connection.opened, 2)

    def test_relation_extra_idempotency_reserved_in_progress_rejects_before_handler(self) -> None:
        idempotency_store = _RecordingIdempotencyStore()
        idempotency_store.reserve(
            tenant_id="default",
            actor_id="finance-user",
            action_name="turnover_relation_extra_update",
            idempotency_key="relation-extra-idem-in-progress",
            request_fingerprint="fingerprint-1",
            request_payload={"relation_id": "turnover_rel_1"},
        )
        idempotency_store.calls.clear()
        uow, deps = self._build_uow(idempotency_store=idempotency_store)

        with self.assertRaises(WorkbenchIdempotencyInProgress):
            self._run_uow(
                uow,
                _Command(
                    action_name="turnover_relation_extra_update",
                    scope_keys=["all"],
                    payload={"relation_id": "turnover_rel_1"},
                    idempotency_key="relation-extra-idem-in-progress",
                    request_fingerprint="fingerprint-1",
                ),
                lambda _context: self.fail("in-progress idempotency must not call handler"),
            )

        self.assertEqual([call["operation"] for call in idempotency_store.calls], ["for_transaction", "reserve"])
        self.assertEqual(deps.connection.opened, 1)
        self.assertEqual(deps.dirty_outbox_writer.calls, [])

    def test_target_confirm_relation_facade_uses_relation_port_and_returns_service_payload(self) -> None:
        relation_port = _RecordingConfirmRelationPort()
        uow, deps = self._build_uow(relation_repository=relation_port)  # type: ignore[arg-type]
        facade = self._write_facade_class()(uow=uow)

        result = facade.confirm_relation(
            bank_row_ids=["bank_txn_1", "bank_txn_2"],
            actor_id="finance-user",
            tenant_id="default",
            note="manual confirm",
            affected_months=["2026-02"],
        )

        self.assertEqual(result["relation"]["status"], "confirmed")
        self.assertEqual(
            relation_port.confirm_calls,
            [
                {
                    "bank_row_ids": ["bank_txn_1", "bank_txn_2"],
                    "actor_id": "finance-user",
                    "note": "manual confirm",
                    "transaction": deps.connection.transaction_obj,
                }
            ],
        )
        self.assertEqual(deps.connection.commits, 1)

    def test_target_confirm_relation_facade_rolls_back_when_dirty_outbox_fails(self) -> None:
        relation_port = _RecordingConfirmRelationPort()
        uow, deps = self._build_uow(
            relation_repository=relation_port,  # type: ignore[arg-type]
            dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True),
        )
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            facade.confirm_relation(
                bank_row_ids=["bank_txn_1", "bank_txn_2"],
                actor_id="finance-user",
                tenant_id="default",
                note="manual confirm",
                affected_months=["2026-02"],
            )

        self.assertEqual(len(relation_port.confirm_calls), 1)
        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_target_confirm_relation_facade_enqueues_turnover_refresh(self) -> None:
        uow, deps = self._build_uow(
            relation_repository=_RecordingConfirmRelationPort(),  # type: ignore[arg-type]
        )
        facade = self._write_facade_class()(uow=uow)

        facade.confirm_relation(
            bank_row_ids=["bank_txn_1", "bank_txn_2"],
            actor_id="finance-user",
            tenant_id="default",
            note="manual confirm",
            affected_months=["2026-02"],
        )

        self.assertEqual(
            [(call["scope_type"], call["scope_keys"], call["reason"]) for call in deps.dirty_outbox_writer.calls],
            [("turnover_ledger", ["2026-02"], "turnover_relation_changed")],
        )

    def test_target_withdraw_relation_facade_uses_relation_port_and_returns_service_payload(self) -> None:
        relation_port = _RecordingWithdrawRelationPort()
        uow, deps = self._build_uow(relation_repository=relation_port)  # type: ignore[arg-type]
        facade = self._write_facade_class()(uow=uow)

        result = facade.withdraw_relation(
            relation_id="turnover_rel_1",
            actor_id="finance-user",
            tenant_id="default",
            note="manual withdraw",
            affected_months=["2026-02"],
        )

        self.assertEqual(result["relation"]["status"], "withdrawn")
        self.assertEqual(
            relation_port.withdraw_calls,
            [
                {
                    "relation_id": "turnover_rel_1",
                    "actor_id": "finance-user",
                    "note": "manual withdraw",
                    "transaction": deps.connection.transaction_obj,
                }
            ],
        )
        self.assertEqual(deps.connection.commits, 1)

    def test_target_withdraw_relation_facade_rolls_back_when_dirty_outbox_fails(self) -> None:
        relation_port = _RecordingWithdrawRelationPort()
        uow, deps = self._build_uow(
            relation_repository=relation_port,  # type: ignore[arg-type]
            dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True),
        )
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            facade.withdraw_relation(
                relation_id="turnover_rel_1",
                actor_id="finance-user",
                tenant_id="default",
                note="manual withdraw",
                affected_months=["2026-02"],
            )

        self.assertEqual(len(relation_port.withdraw_calls), 1)
        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_target_withdraw_relation_facade_enqueues_turnover_and_workbench_refreshes(self) -> None:
        uow, deps = self._build_uow(
            relation_repository=_RecordingWithdrawRelationPort(),  # type: ignore[arg-type]
        )
        facade = self._write_facade_class()(uow=uow)

        facade.withdraw_relation(
            relation_id="turnover_rel_1",
            actor_id="finance-user",
            tenant_id="default",
            note="manual withdraw",
            affected_months=["2026-02"],
        )

        self.assertEqual(
            [(call["scope_type"], call["scope_keys"], call["reason"]) for call in deps.dirty_outbox_writer.calls],
            [
                ("turnover_ledger", ["2026-02"], "turnover_relation_changed"),
                ("workbench", ["2026-02"], "turnover_relation_changed"),
                ("workbench_relation", ["2026-02"], "turnover_relation_changed"),
                ("cost_statistics", ["active:2026-02"], "cost_statistics_relation_delta"),
                ("search", ["2026-02"], "turnover_relation_changed"),
            ],
        )
        self.assertEqual(len(deps.dirty_outbox_writer.batch_calls), 1)
        self.assertIs(
            deps.dirty_outbox_writer.batch_calls[0]["transaction"],
            deps.connection.transaction_obj,
        )

    def test_target_confirm_relation_facade_passes_expected_versions_before_repository(self) -> None:
        # PF-P173 target contract: confirm should accept bank-row expected versions and reject stale submits before mutation.
        stale_precondition = _StalePreconditionPort(stale=True)
        relation_port = _RecordingConfirmRelationPort()
        uow, deps = self._build_uow(
            relation_repository=relation_port,  # type: ignore[arg-type]
            stale_precondition_port=stale_precondition,
        )
        facade = self._write_facade_class()(uow=uow)
        expected_versions = {"turnover_bank_row:bank_txn_1": "v1", "turnover_bank_row:bank_txn_2": "v1"}

        with self.assertRaisesRegex(RuntimeError, "turnover_write_conflict"):
            facade.confirm_relation(
                bank_row_ids=["bank_txn_1", "bank_txn_2"],
                actor_id="finance-user",
                tenant_id="default",
                note="stale confirm",
                affected_months=["2026-02"],
                expected_versions=expected_versions,
            )

        self.assertEqual(
            stale_precondition.checked,
            [{"expected_versions": expected_versions, "transaction": deps.connection.transaction_obj}],
        )
        self.assertEqual(relation_port.confirm_calls, [])
        self.assertEqual(deps.dirty_outbox_writer.calls, [])
        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero(self) -> None:
        module = self._write_adapters_module()
        requested_ids: list[list[str]] = []

        def load_rows(row_ids: list[str]) -> list[dict[str, object]]:
            requested_ids.append(list(row_ids))
            return [
                {
                    "id": "bank_txn_1",
                    "category_version": 0,
                    "manual_category_version": 9,
                }
            ]

        port = module.TurnoverLedgerBankRowSelectionPort(
            bank_rows_by_ids_provider=load_rows
        )

        port.assert_current(
            expected_versions={"turnover_bank_row:bank_txn_1": 9},
            transaction=object(),
        )
        self.assertEqual(requested_ids, [["bank_txn_1"]])

    def test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero(self) -> None:
        module = self._write_adapters_module()
        requested_ids: list[list[str]] = []

        def load_rows(row_ids: list[str]) -> list[dict[str, object]]:
            requested_ids.append(list(row_ids))
            return [
                {
                    "id": "bank_txn_1",
                    "category_version": 0,
                    "manual_category_version": 0,
                    "version": 5,
                }
            ]

        port = module.TurnoverLedgerBankRowSelectionPort(
            bank_rows_by_ids_provider=load_rows
        )

        port.assert_current(
            expected_versions={"turnover_bank_row:bank_txn_1": 5},
            transaction=object(),
        )
        self.assertEqual(requested_ids, [["bank_txn_1"]])

    def test_bank_row_selection_reuses_the_version_checked_rows_for_relation_preview(self) -> None:
        module = self._write_adapters_module()
        requested_ids: list[list[str]] = []

        def load_rows(row_ids: list[str]) -> list[dict[str, object]]:
            requested_ids.append(list(row_ids))
            return [{"id": "bank_txn_1", "category_version": 5}]

        port = module.TurnoverLedgerBankRowSelectionPort(
            bank_rows_by_ids_provider=load_rows
        )

        port.assert_current(
            expected_versions={"turnover_bank_row:bank_txn_1": 5},
            transaction=object(),
        )
        rows = port.rows_by_ids(["bank_txn_1"])
        rows[0]["category_version"] = 99

        self.assertEqual(requested_ids, [["bank_txn_1"]])
        self.assertEqual(port.rows_by_ids(["bank_txn_1"])[0]["category_version"], 5)

    def test_target_confirm_relation_facade_passes_idempotency_before_repository(self) -> None:
        # PF-P177 target contract: confirm should reserve/replay/conflict by durable idempotency before repository save.
        class _CommandCapturingUoW:
            def __init__(self) -> None:
                self.commands: list[object] = []
                self.confirm_calls: list[dict[str, object]] = []

            def run(self, command: object, handler: Callable[[object], object]) -> object:
                self.commands.append(command)
                assert getattr(command, "idempotency_key") == "confirm-idem-1"
                assert getattr(command, "actor_id") == "finance-user"
                assert getattr(command, "tenant_id") == "default"
                assert getattr(command, "action_name") == "turnover_relation_confirm"
                assert getattr(command, "request_fingerprint")
                return handler(
                    SimpleNamespace(
                        transaction=object(),
                        relation_repository=SimpleNamespace(confirm_relation=self.confirm_relation),
                    )
                )

            def confirm_relation(
                self,
                *,
                bank_row_ids: list[str],
                actor_id: str,
                note: str | None,
                transaction: object,
            ) -> dict[str, object]:
                self.confirm_calls.append(
                    {
                        "bank_row_ids": list(bank_row_ids),
                        "actor_id": actor_id,
                        "note": note,
                        "transaction": transaction,
                    }
                )
                return {"relation_id": "turnover_rel_confirm_idem"}

        uow = _CommandCapturingUoW()
        facade = self._write_facade_class()(uow=uow)

        result = facade.confirm_relation(
            bank_row_ids=["bank_txn_1", "bank_txn_2"],
            actor_id="finance-user",
            tenant_id="default",
            note="idempotent confirm",
            affected_months=["2026-02"],
            expected_versions={"turnover_bank_row:bank_txn_1": 1},
            idempotency_key="confirm-idem-1",
        )

        self.assertEqual(result["relation_id"], "turnover_rel_confirm_idem")
        self.assertEqual(len(uow.commands), 1)
        self.assertEqual(len(uow.confirm_calls), 1)

    def test_target_zero_difference_closure_facade_writes_only_canonical_workbench_relation(self) -> None:
        class _CommandCapturingUoW:
            def __init__(self) -> None:
                self.commands: list[object] = []
                self.closure_calls: list[dict[str, object]] = []
                self.pair_calls: list[dict[str, object]] = []

            def run(self, command: object, handler: Callable[[object], object]) -> object:
                self.commands.append(command)
                assert getattr(command, "action_name") == "turnover_relation_zero_difference_closure"
                assert getattr(command, "expected_versions") == {"turnover_bank_row:bank_txn_1": "v1"}
                assert getattr(command, "idempotency_key") == "closure-idem-1"
                assert getattr(command, "request_fingerprint")
                assert [
                    (request["scope_type"], request["scope_keys"], request["reason"])
                    for request in getattr(command, "refresh_requests")
                ] == [
                    ("turnover_ledger", ["2026-02"], "turnover_closure_changed"),
                    ("workbench", ["2026-02"], "turnover_closure_changed"),
                    ("workbench_relation", ["2026-02"], "turnover_closure_changed"),
                    ("cost_statistics", ["active:2026-02"], "cost_statistics_relation_delta"),
                    ("search", ["2026-02"], "turnover_closure_changed"),
                ]
                return handler(
                    SimpleNamespace(
                        transaction=object(),
                        relation_repository=SimpleNamespace(
                            preview_zero_difference_closure=self.preview_zero_difference_closure,
                        ),
                        workbench_pair_port=SimpleNamespace(
                            prepare_turnover_manual_closure_write=self.prepare_turnover_manual_closure_write,
                            create_turnover_manual_closure=self.create_turnover_manual_closure,
                        ),
                    )
                )

            @staticmethod
            def prepare_turnover_manual_closure_write(**_kwargs: object) -> object:
                return SimpleNamespace(preparation_id="prepared-closure")

            def preview_zero_difference_closure(
                self,
                *,
                bank_row_ids: list[str],
                actor_id: str,
                note: str | None,
                transaction: object,
            ) -> dict[str, object]:
                self.closure_calls.append(
                    {
                        "bank_row_ids": list(bank_row_ids),
                        "actor_id": actor_id,
                        "note": note,
                        "transaction": transaction,
                    }
                )
                return {
                    "closure": {
                        "relation_id": "turnover_rel_closure",
                        "bank_row_ids": list(bank_row_ids),
                        "principal_amount": "100.00",
                        "settled_amount": "100.00",
                    }
                }

            def create_turnover_manual_closure(
                self,
                *,
                closure: dict[str, object],
                bank_row_ids: list[str],
                actor_id: str,
                note: str | None,
                affected_months: list[str],
                transaction: object,
                preparation: object,
            ) -> dict[str, object]:
                self.pair_calls.append(
                    {
                        "closure_id": closure.get("relation_id"),
                        "bank_row_ids": list(bank_row_ids),
                        "actor_id": actor_id,
                        "note": note,
                        "affected_months": list(affected_months),
                        "transaction": transaction,
                        "preparation": preparation,
                    }
                )
                return {
                    "case_id": "turnover:turnover_rel_closure",
                    "relation_mode": "turnover_manual_closure",
                }

        uow = _CommandCapturingUoW()
        facade = self._write_facade_class()(uow=uow)

        result = facade.confirm_zero_difference_closure(
            bank_row_ids=["bank_txn_1", "bank_txn_2"],
            actor_id="finance-user",
            tenant_id="default",
            note="manual closure",
            affected_months=["2026-02"],
            expected_versions={"turnover_bank_row:bank_txn_1": "v1"},
            idempotency_key="closure-idem-1",
        )

        self.assertNotIn("turnover_relation", result)
        self.assertNotIn("relation", result)
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["workbench_pair_relation"]["relation_mode"], "turnover_manual_closure")
        self.assertEqual(len(uow.commands), 1)
        self.assertEqual(len(uow.closure_calls), 1)
        self.assertEqual(len(uow.pair_calls), 1)
        self.assertEqual(uow.pair_calls[0]["closure_id"], "turnover_rel_closure")
        self.assertEqual(uow.pair_calls[0]["affected_months"], ["2026-02"])
        self.assertEqual(getattr(uow.pair_calls[0]["preparation"], "preparation_id"), "prepared-closure")

    def test_cash_closure_withdraw_uses_exact_month_targets(self) -> None:
        class _CommandCapturingUoW:
            def __init__(self) -> None:
                self.command: object | None = None

            def run(self, command: object, handler: Callable[[object], object]) -> object:
                self.command = command
                return handler(
                    SimpleNamespace(
                        transaction=object(),
                        workbench_pair_port=SimpleNamespace(
                            withdraw_cash_closure_case=lambda **_kwargs: {
                                "case_id": "turnover:case-1",
                                "status": "cancelled",
                            }
                        ),
                    )
                )

        uow = _CommandCapturingUoW()
        facade = self._write_facade_class()(uow=uow)

        result = facade.withdraw_cash_closure_case(
            cash_closure_case_id="turnover:case-1",
            actor_id="finance-user",
            tenant_id="default",
            note="withdraw",
            affected_months=["2026-02", "2026-03"],
        )

        self.assertEqual(result["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(getattr(uow.command, "scope_keys"), ["2026-02", "2026-03"])
        self.assertEqual(
            [
                (request["scope_type"], request["scope_keys"])
                for request in getattr(uow.command, "refresh_requests")
            ],
            [
                ("turnover_ledger", ["2026-02", "2026-03"]),
                ("workbench", ["2026-02", "2026-03"]),
                ("workbench_relation", ["2026-02", "2026-03"]),
                ("cost_statistics", ["active:2026-02", "active:2026-03"]),
                ("search", ["2026-02", "2026-03"]),
            ],
        )

    def test_closure_request_boundary_returns_workbench_visibility_freshness_targets(self) -> None:
        module = self._write_adapters_module()

        class _RecordingClosureFacade:
            def __init__(self) -> None:
                self.withdraw_calls: list[dict[str, object]] = []

            def confirm_zero_difference_closure(self, **kwargs: object) -> dict[str, object]:
                return {
                    "status": "confirmed",
                    "workbench_pair_relation": {
                        "case_id": "turnover:turnover_rel_closure",
                        "relation_mode": "turnover_manual_closure",
                    },
                    "received_affected_months": list(kwargs.get("affected_months") or []),
                }

            def withdraw_cash_closure_case(self, **kwargs: object) -> dict[str, object]:
                self.withdraw_calls.append(dict(kwargs))
                return {"status": "withdrawn"}

        facade = _RecordingClosureFacade()
        boundary = module.TurnoverLedgerConfirmRequestBoundaryFacade(
            facade=facade,
            affected_months_resolver=lambda _row_ids: ["2026-02", "2026-02", "2026-03"],
            cash_closure_relation_provider=lambda _case_id: {
                "case_id": "turnover:turnover_rel_closure",
                "row_ids": ["oa-1", "bank_txn_income", "bank_txn_expense"],
                "row_types": ["oa", "bank", "bank"],
                "special_metadata": {},
            },
        )

        result = boundary.confirm_zero_difference_closure_from_request(
            bank_row_ids=["bank_txn_income", "bank_txn_expense", "bank_txn_settlement"],
            actor_id="finance-user",
            tenant_id="default",
            note="manual closure",
            expected_versions={"turnover_bank_row:bank_txn_income": "v1"},
            idempotency_key="closure-idem-1",
        )

        self.assertEqual(result["affected_months"], ["2026-02", "2026-02", "2026-03"])
        self.assertEqual(
            result["freshness_targets"],
            [
                {"read_model_key": "turnover_ledger", "scope_key": "2026-02"},
                {"read_model_key": "turnover_ledger", "scope_key": "2026-03"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-02"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-03"},
            ],
        )
        self.assertEqual(result["affected_scope_keys"], ["2026-02", "2026-03"])
        self.assertEqual(result["operation_barrier_targets"], result["freshness_targets"])

        withdrawn = boundary.withdraw_cash_closure_case_from_request(
            cash_closure_case_id="turnover:turnover_rel_closure",
            actor_id="finance-user",
            tenant_id="default",
            note="withdraw",
        )

        self.assertEqual(withdrawn["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(withdrawn["operation_barrier_targets"], result["operation_barrier_targets"])
        self.assertEqual(facade.withdraw_calls[0]["affected_months"], ["2026-02", "2026-03"])

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

    def test_target_withdraw_relation_facade_passes_expected_versions_before_repository(self) -> None:
        # PF-P099 target contract: facade should expose expected_versions and let UoW reject stale withdraw.
        stale_precondition = _StalePreconditionPort(stale=True)
        relation_port = _RecordingWithdrawRelationPort()
        uow, deps = self._build_uow(
            relation_repository=relation_port,  # type: ignore[arg-type]
            stale_precondition_port=stale_precondition,
        )
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "turnover_write_conflict"):
            facade.withdraw_relation(
                relation_id="turnover_rel_1",
                actor_id="finance-user",
                tenant_id="default",
                note="duplicate withdraw",
                affected_months=["2026-02"],
                expected_versions={"relation:turnover_rel_1": 3},
            )

        self.assertEqual(
            stale_precondition.checked,
            [{"expected_versions": {"relation:turnover_rel_1": 3}, "transaction": deps.connection.transaction_obj}],
        )
        self.assertEqual(relation_port.withdraw_calls, [])
        self.assertEqual(deps.dirty_outbox_writer.calls, [])
        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_target_withdraw_relation_facade_passes_idempotency_before_repository(self) -> None:
        # PF-P179 target contract: withdraw should reserve/replay/conflict by durable idempotency before repository save.
        class _CommandCapturingUoW:
            def __init__(self) -> None:
                self.commands: list[object] = []
                self.withdraw_calls: list[dict[str, object]] = []

            def run(self, command: object, handler: Callable[[object], object]) -> object:
                self.commands.append(command)
                assert getattr(command, "idempotency_key") == "withdraw-idem-1"
                assert getattr(command, "actor_id") == "finance-user"
                assert getattr(command, "tenant_id") == "default"
                assert getattr(command, "action_name") == "turnover_relation_withdraw"
                assert getattr(command, "request_fingerprint")
                return handler(
                    SimpleNamespace(
                        transaction=object(),
                        relation_repository=SimpleNamespace(withdraw_relation=self.withdraw_relation),
                    )
                )

            def withdraw_relation(
                self,
                *,
                relation_id: str,
                actor_id: str,
                note: str | None,
                transaction: object,
            ) -> dict[str, object]:
                self.withdraw_calls.append(
                    {
                        "relation_id": relation_id,
                        "actor_id": actor_id,
                        "note": note,
                        "transaction": transaction,
                    }
                )
                return {"relation": {"relation_id": relation_id, "status": "withdrawn"}}

        uow = _CommandCapturingUoW()
        facade = self._write_facade_class()(uow=uow)

        result = facade.withdraw_relation(
            relation_id="turnover_rel_1",
            actor_id="finance-user",
            tenant_id="default",
            note="idempotent withdraw",
            affected_months=["2026-02"],
            expected_versions={"relation:turnover_rel_1": 3},
            idempotency_key="withdraw-idem-1",
        )

        self.assertEqual(result["relation"]["status"], "withdrawn")
        self.assertEqual(len(uow.commands), 1)
        self.assertEqual(len(uow.withdraw_calls), 1)

    def test_target_withdraw_relation_facade_cancels_bank_only_workbench_relation(self) -> None:
        class _CommandCapturingUoW:
            def __init__(self) -> None:
                self.commands: list[object] = []
                self.withdraw_calls: list[dict[str, object]] = []
                self.precheck_calls: list[dict[str, object]] = []
                self.cancel_calls: list[dict[str, object]] = []

            def run(self, command: object, handler: Callable[[object], object]) -> object:
                self.commands.append(command)
                assert [
                    (request["scope_type"], request["scope_keys"], request["reason"])
                    for request in getattr(command, "refresh_requests")
                ] == [
                    ("turnover_ledger", ["2026-02"], "turnover_relation_changed"),
                    ("workbench", ["2026-02"], "turnover_relation_changed"),
                    ("workbench_relation", ["2026-02"], "turnover_relation_changed"),
                    ("cost_statistics", ["active:2026-02"], "cost_statistics_relation_delta"),
                    ("search", ["2026-02"], "turnover_relation_changed"),
                ]
                return handler(
                    SimpleNamespace(
                        transaction=object(),
                        relation_repository=SimpleNamespace(withdraw_relation=self.withdraw_relation),
                        workbench_pair_port=SimpleNamespace(
                            assert_turnover_manual_closure_withdrawable=self.assert_turnover_manual_closure_withdrawable,
                            withdraw_turnover_manual_closure=self.withdraw_turnover_manual_closure,
                        ),
                    )
                )

            def assert_turnover_manual_closure_withdrawable(
                self,
                *,
                relation_id: str,
                transaction: object,
            ) -> None:
                self.precheck_calls.append({"relation_id": relation_id, "transaction": transaction})

            def withdraw_relation(
                self,
                *,
                relation_id: str,
                actor_id: str,
                note: str | None,
                transaction: object,
            ) -> dict[str, object]:
                self.withdraw_calls.append(
                    {
                        "relation_id": relation_id,
                        "actor_id": actor_id,
                        "note": note,
                        "transaction": transaction,
                    }
                )
                return {
                    "relation": {
                        "relation_id": relation_id,
                        "status": "withdrawn",
                        "bank_row_ids": ["bank_txn_1", "bank_txn_2"],
                    }
                }

            def withdraw_turnover_manual_closure(
                self,
                *,
                relation: dict[str, object],
                actor_id: str,
                note: str | None,
                transaction: object,
            ) -> dict[str, object]:
                self.cancel_calls.append(
                    {
                        "relation_id": relation.get("relation_id"),
                        "actor_id": actor_id,
                        "note": note,
                        "transaction": transaction,
                    }
                )
                return {"case_id": "turnover:turnover_rel_1", "status": "cancelled"}

        uow = _CommandCapturingUoW()
        facade = self._write_facade_class()(uow=uow)

        result = facade.withdraw_relation(
            relation_id="turnover_rel_1",
            actor_id="finance-user",
            tenant_id="default",
            note="withdraw bank-only closure",
            affected_months=["2026-02"],
        )

        self.assertEqual(result["relation"]["status"], "withdrawn")
        self.assertEqual(result["workbench_pair_relation"]["status"], "cancelled")
        self.assertEqual([call["relation_id"] for call in uow.precheck_calls], ["turnover_rel_1"])
        self.assertEqual([call["relation_id"] for call in uow.withdraw_calls], ["turnover_rel_1"])
        self.assertEqual([call["relation_id"] for call in uow.cancel_calls], ["turnover_rel_1"])

    def test_target_withdraw_relation_facade_rejects_after_workbench_relation_is_upgraded(self) -> None:
        class _CommandCapturingUoW:
            def __init__(self) -> None:
                self.withdraw_calls: list[dict[str, object]] = []

            def run(self, command: object, handler: Callable[[object], object]) -> object:
                _ = command
                return handler(
                    SimpleNamespace(
                        transaction=object(),
                        relation_repository=SimpleNamespace(withdraw_relation=self.withdraw_relation),
                        workbench_pair_port=SimpleNamespace(
                            assert_turnover_manual_closure_withdrawable=self.assert_turnover_manual_closure_withdrawable,
                        ),
                    )
                )

            def assert_turnover_manual_closure_withdrawable(
                self,
                *,
                relation_id: str,
                transaction: object,
            ) -> None:
                _ = relation_id, transaction
                raise RuntimeError("turnover_closure_withdraw_requires_workbench")

            def withdraw_relation(
                self,
                *,
                relation_id: str,
                actor_id: str,
                note: str | None,
                transaction: object,
            ) -> dict[str, object]:
                self.withdraw_calls.append(
                    {
                        "relation_id": relation_id,
                        "actor_id": actor_id,
                        "note": note,
                        "transaction": transaction,
                    }
                )
                return {"relation": {"relation_id": relation_id, "status": "withdrawn"}}

        uow = _CommandCapturingUoW()
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "turnover_closure_withdraw_requires_workbench"):
            facade.withdraw_relation(
                relation_id="turnover_rel_1",
                actor_id="finance-user",
                tenant_id="default",
                note="should use workbench",
                affected_months=["2026-02"],
            )

        self.assertEqual(uow.withdraw_calls, [])

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

    def test_tag_selection_settings_port_uses_uow_transaction_before_dirty_outbox(self) -> None:
        uow, deps = self._build_uow()

        def handler(context: object) -> dict[str, object]:
            transaction = getattr(context, "transaction")
            context.settings_port.save_tag_selection_settings(
                next_snapshot={"turnover_ledger_tag_selection": {"version": 2}},
                audit_event={"action": "turnover_ledger_tag_selection_changed"},
                transaction=transaction,
            )
            return {
                "version": 2,
                "selected_tag_codes": ["external_rule_borrow_out"],
                "active_tags": [{"code": "external_rule_borrow_out", "label": "借出款"}],
            }

        result = self._run_uow(
            uow,
            _Command(action_name="turnover_ledger_tag_selection_changed", scope_keys=["all"]),
            handler,
        )

        self.assertEqual(result["version"], 2)
        self.assertEqual(result["selected_tag_codes"], ["external_rule_borrow_out"])
        self.assertEqual(result["active_tags"][0]["code"], "external_rule_borrow_out")
        forbidden_keys = {"headers", "cookies", "cookie", "response", "status_code", "http_status", "auth"}
        self.assertTrue(forbidden_keys.isdisjoint(result))
        self.assertEqual(deps.connection.commits, 1)
        self.assertIs(deps.settings_port.saved[0]["transaction"], deps.connection.transaction_obj)
        self.assertIs(deps.dirty_outbox_writer.calls[0]["transaction"], deps.connection.transaction_obj)
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["reason"], "turnover_ledger_tag_selection_changed")

    def test_tag_selection_pure_normalizer_returns_next_selection_without_mutating_settings_snapshot(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.app_settings_service")
        service_class = getattr(module, "AppSettingsService")
        state_store = _AppSettingsStateStore(_tag_selection_settings_payload())
        service = service_class(
            state_store=state_store,
            project_costing_service=_ProjectCostingStub(),
        )

        before_payload = service.get_turnover_ledger_tag_selection_payload()
        normalized = service.normalize_turnover_ledger_tag_selection_update(
            {
                "expected_version": before_payload["version"],
                "selected_tag_codes": ["external_rule_borrow_out"],
            },
            actor_id="finance-user",
        )

        self.assertEqual(normalized["next_selection"]["selected_tag_codes"], ["external_rule_borrow_out"])
        self.assertEqual(normalized["audit_event"]["actor_id"], "finance-user")
        self.assertEqual(normalized["audit_event"]["old_version"], before_payload["version"])
        self.assertEqual(normalized["audit_event"]["new_version"], before_payload["version"] + 1)
        self.assertEqual(normalized["public_payload"]["selected_tag_codes"], ["external_rule_borrow_out"])
        self.assertEqual(state_store.saved_payloads, [])
        self.assertEqual(service.get_turnover_ledger_tag_selection_payload(), before_payload)

        updated = service.update_turnover_ledger_tag_selection(
            {
                "expected_version": before_payload["version"],
                "selected_tag_codes": ["external_rule_borrow_out"],
            },
            actor_id="finance-user",
        )

        self.assertEqual(updated["selected_tag_codes"], ["external_rule_borrow_out"])
        self.assertEqual(len(state_store.saved_payloads), 1)

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

    def test_bank_row_tags_facade_uses_bankdetail_port_and_returns_service_payload(self) -> None:
        uow, deps = self._build_uow(
            bankdetail_port=_RecordingBankdetailPort(
                result={"updated_categories": [{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}]}
            )
        )
        facade = self._write_facade_class()(uow=uow)

        result = facade.update_bank_row_tags_batch(
            updates=[{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}],
            actor_id="finance-user",
            tenant_id="default",
            affected_months=["2026-02"],
        )

        self.assertEqual(result["updated_categories"], [{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}])
        self.assertEqual(deps.connection.commits, 1)
        self.assertEqual(deps.bankdetail_port.category_updates[0]["updates"], [{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}])
        self.assertEqual(deps.bankdetail_port.category_updates[0]["actor_id"], "finance-user")
        self.assertIs(deps.bankdetail_port.category_updates[0]["transaction"], deps.connection.transaction_obj)
        self.assertTrue({"headers", "cookies", "response", "status_code"}.isdisjoint(result))

    def test_bank_row_tags_facade_rolls_back_when_dirty_outbox_fails(self) -> None:
        uow, deps = self._build_uow(dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True))
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            facade.update_bank_row_tags_batch(
                updates=[{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}],
                actor_id="finance-user",
                tenant_id="default",
                affected_months=["2026-02"],
            )

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_bank_row_tags_facade_enqueues_bankdetail_workbench_and_turnover_refreshes(self) -> None:
        uow, deps = self._build_uow()
        facade = self._write_facade_class()(uow=uow)

        facade.update_bank_row_tags_batch(
            updates=[{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}],
            actor_id="finance-user",
            tenant_id="default",
            affected_months=["2026-02", "2026-03"],
        )

        self.assertEqual(
            [
                (call["scope_type"], call["scope_keys"], call["reason"])
                for call in deps.dirty_outbox_writer.calls
            ],
            [
                ("bank_detail", ["2026-02", "2026-03"], "bank_transaction_category_changed"),
                ("bank_flow_rule_batch", ["2026-02", "2026-03"], "bank_transaction_category_changed"),
                ("workbench", ["2026-02", "2026-03"], "bank_transaction_category_changed"),
                ("workbench_relation", ["2026-02", "2026-03"], "bank_transaction_category_changed"),
                ("invoice_lifecycle", ["2026-02", "2026-03"], "bank_transaction_category_changed"),
                (
                    "cost_statistics",
                    ["active:2026-02", "all:2026-02", "active:2026-03", "all:2026-03"],
                    "bank_transaction_category_changed",
                ),
                ("search", ["2026-02", "2026-03"], "bank_transaction_category_changed"),
                ("turnover_ledger", ["2026-02", "2026-03"], "bank_transaction_category_changed"),
                (
                    "pending_invoice",
                    [
                        "expense:all:2026-02",
                        "income:all:2026-02",
                        "income:cash_income:2026-02",
                        "expense:all:2026-03",
                        "income:all:2026-03",
                        "income:cash_income:2026-03",
                    ],
                    "bank_transaction_category_changed",
                ),
            ],
        )

    def test_target_bank_row_tags_facade_passes_idempotency_before_bankdetail_port(self) -> None:
        idempotency_store = _RecordingIdempotencyStore()
        uow, deps = self._build_uow(idempotency_store=idempotency_store)
        facade = self._write_facade_class()(uow=uow)

        result = facade.update_bank_row_tags_batch(
            updates=[
                {
                    "transaction_id": "bank_txn_1",
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                }
            ],
            actor_id="finance-user",
            tenant_id="default",
            affected_months=["2026-02"],
            idempotency_key="bank-row-tags-idem-1",
        )

        self.assertEqual(result["updated_categories"], [{"transaction_id": "bank_txn_1"}])
        self.assertEqual(
            [call["operation"] for call in idempotency_store.calls],
            ["for_transaction", "reserve", "commit"],
        )
        self.assertEqual(len(deps.bankdetail_port.category_updates), 1)
        self.assertEqual(deps.bankdetail_port.category_updates[0]["actor_id"], "finance-user")

    def test_uow_constructor_requires_granular_ports_not_application_god_object(self) -> None:
        uow_class = self._uow_class()

        with self.assertRaises(TypeError):
            uow_class(application=object())

    def test_relation_extra_write_facade_constructor_rejects_application_god_object(self) -> None:
        # PF-P056 target contract: PF-P057 should implement the facade and remove this expectedFailure.
        facade_class = self._write_facade_class()

        with self.assertRaises(TypeError):
            facade_class(application=object())

    def test_tag_selection_write_facade_commits_settings_and_dirty_outbox_in_one_uow(self) -> None:
        uow, deps = self._build_uow()
        normalizer = _RecordingTagSelectionNormalizer()
        facade = self._write_facade_class()(uow=uow, tag_selection_normalizer=normalizer)

        result = facade.update_tag_selection(
            payload={"expected_version": 1, "selected_tag_codes": ["external_rule_borrow_out"]},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
        )

        self.assertEqual(
            normalizer.calls,
            [
                {
                    "payload": {"expected_version": 1, "selected_tag_codes": ["external_rule_borrow_out"]},
                    "actor_id": "finance-user",
                }
            ],
        )
        self.assertEqual(result["selected_tag_codes"], ["external_rule_borrow_out"])
        self.assertEqual(result["active_tags"][0]["code"], "external_rule_borrow_out")
        self.assertEqual(deps.connection.commits, 1)
        self.assertEqual(deps.connection.rollbacks, 0)
        self.assertIs(deps.settings_port.saved[0]["transaction"], deps.connection.transaction_obj)
        self.assertEqual(
            deps.settings_port.saved[0]["next_snapshot"],
            {
                "turnover_ledger_tag_selection": {
                    "version": 2,
                    "selected_tag_codes": ["external_rule_borrow_out"],
                }
            },
        )
        self.assertIs(deps.dirty_outbox_writer.calls[0]["transaction"], deps.connection.transaction_obj)
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["reason"], "turnover_ledger_tag_selection_changed")
        forbidden_keys = {"headers", "cookies", "cookie", "response", "status_code", "http_status", "auth"}
        self.assertTrue(forbidden_keys.isdisjoint(result))

    def test_tag_selection_write_facade_rolls_back_settings_when_dirty_outbox_fails(self) -> None:
        uow, deps = self._build_uow(dirty_outbox_writer=_RecordingDirtyOutboxWriter(fail=True))
        facade = self._write_facade_class()(
            uow=uow,
            tag_selection_normalizer=_RecordingTagSelectionNormalizer(),
        )

        with self.assertRaisesRegex(RuntimeError, "forced dirty/outbox failure"):
            facade.update_tag_selection(
                payload={"expected_version": 1, "selected_tag_codes": ["external_rule_borrow_out"]},
                actor_id="finance-user",
                tenant_id="default",
                scope_keys=["all"],
            )

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_tag_selection_write_facade_normalization_error_prevents_uow_side_effects(self) -> None:
        uow, deps = self._build_uow()
        facade = self._write_facade_class()(
            uow=uow,
            tag_selection_normalizer=_RecordingTagSelectionNormalizer(fail=True),
        )

        with self.assertRaisesRegex(ValueError, "invalid tag selection"):
            facade.update_tag_selection(
                payload={"expected_version": 1, "selected_tag_codes": ["fee"]},
                actor_id="finance-user",
                tenant_id="default",
                scope_keys=["all"],
            )

        self.assertEqual(deps.connection.opened, 0)
        self.assertEqual(deps.settings_port.saved, [])
        self.assertEqual(deps.dirty_outbox_writer.calls, [])

    def test_target_tag_selection_facade_passes_idempotency_before_settings_port(self) -> None:
        idempotency_store = _RecordingIdempotencyStore()
        uow, deps = self._build_uow(idempotency_store=idempotency_store)
        facade = self._write_facade_class()(
            uow=uow,
            tag_selection_normalizer=_RecordingTagSelectionNormalizer(),
        )

        result = facade.update_tag_selection(
            payload={"expected_version": 1, "selected_tag_codes": ["external_rule_borrow_out"]},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
            idempotency_key="tag-selection-idem-1",
        )

        self.assertEqual(result["selected_tag_codes"], ["external_rule_borrow_out"])
        self.assertEqual(
            [call["operation"] for call in idempotency_store.calls],
            ["for_transaction", "reserve", "commit"],
        )
        self.assertEqual(len(deps.settings_port.saved), 1)
        self.assertIs(deps.settings_port.saved[0]["transaction"], deps.connection.transaction_obj)
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["reason"], "turnover_ledger_tag_selection_changed")

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
        self.assertEqual(deps.dirty_outbox_writer.calls[0]["reason"], "turnover_relation_extra_changed")
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

    def test_target_relation_extra_facade_passes_expected_versions_before_repository(self) -> None:
        # PF-P102 target contract: stale relation extra checks must run before repository save.
        stale_precondition = _StalePreconditionPort(stale=True)
        uow, deps = self._build_uow(stale_precondition_port=stale_precondition)
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "turnover_write_conflict"):
            facade.update_relation_extra(
                relation_id="turnover_rel_1",
                payload={"note": "stale extra"},
                actor_id="finance-user",
                tenant_id="default",
                scope_keys=["all"],
                expected_versions={"turnover_relation_extra:turnover_rel_1": "2026-06-02T00:00:00+00:00"},
            )

        self.assertEqual(
            stale_precondition.checked,
            [
                {
                    "expected_versions": {
                        "turnover_relation_extra:turnover_rel_1": "2026-06-02T00:00:00+00:00"
                    },
                    "transaction": deps.connection.transaction_obj,
                }
            ],
        )
        self.assertEqual(deps.extra_repository.extras, [])
        self.assertEqual(deps.dirty_outbox_writer.calls, [])
        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)

    def test_target_relation_extra_facade_passes_idempotency_before_repository(self) -> None:
        # PF-P105 target contract: durable idempotency should reserve/replay/conflict before repository save.
        class _CommandCapturingUoW:
            def __init__(self) -> None:
                self.commands: list[object] = []
                self.extra_repository = _RecordingExtraRepository()

            def run(self, command: object, handler: Callable[[object], object]) -> object:
                self.commands.append(command)
                self.assert_command(command)
                return handler(
                    SimpleNamespace(
                        transaction=object(),
                        extra_repository=self.extra_repository,
                    )
                )

            def assert_command(self, command: object) -> None:
                self_command = command
                assert getattr(self_command, "idempotency_key") == "relation-extra-idem-1"
                assert getattr(self_command, "actor_id") == "finance-user"
                assert getattr(self_command, "tenant_id") == "default"
                assert getattr(self_command, "action_name") == "turnover_relation_extra_update"
                assert getattr(self_command, "request_fingerprint")

        uow = _CommandCapturingUoW()
        facade = self._write_facade_class()(uow=uow)

        result = facade.update_relation_extra(
            relation_id="turnover_rel_1",
            payload={"note": "idempotent extra"},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
            idempotency_key="relation-extra-idem-1",
        )

        self.assertEqual(result["extra"]["relation_id"], "turnover_rel_1")
        self.assertEqual(len(uow.commands), 1)
        self.assertEqual(len(uow.extra_repository.extras), 1)

    def test_target_relation_extra_primary_builder_injects_transactional_stale_precondition_port(self) -> None:
        # PF-P186 target contract: the primary relation extra facade should not rely
        # solely on request-boundary stale checks. The generated UoW must receive an
        # explicit relation-extra stale port so expected_versions are checked in the
        # same transaction before repository save and dirty/outbox enqueue.
        adapters = self._write_adapters_module()
        connection = _RecordingConnection()
        queue_repository = SimpleNamespace(
            enqueue_read_model_refresh_in_transaction=lambda **kwargs: kwargs,
        )

        builder = adapters.TurnoverLedgerRelationExtraPrimaryWriteFacadeBuilder(
            state_store=SimpleNamespace(storage_backend="postgres", _connection=connection),
            queue_repository=queue_repository,
            routes=SimpleNamespace(),
            replace_snapshot=lambda _snapshot: None,
            emit_persistence_warning=lambda **_kwargs: None,
            extra_service=SimpleNamespace(),
            row_provider=lambda **_kwargs: {"relation_id": "turnover_rel_1"},
            current_extra_reader=lambda _relation_id: {
                "extra": {"relation_id": "turnover_rel_1", "updated_at": "2026-06-03T00:00:00+00:00"}
            },
            tenant_id="default",
            postgres_extra_repository_factory=lambda _transaction: _RecordingExtraRepository(),
            postgres_idempotency_store_factory=lambda _connection: InMemoryWorkbenchIdempotencyRepository(),
            local_idempotency_store_provider=InMemoryWorkbenchIdempotencyRepository,
        )

        facade = builder.build()
        self.assertIsNotNone(facade)
        stale_port = getattr(getattr(facade, "_uow"), "_stale_precondition_port")

        self.assertNotIsInstance(stale_port, SimpleNamespace)
        self.assertRegex(type(stale_port).__name__, r"RelationExtra.*StalePreconditionPort")

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

    def test_relation_extra_write_facade_saves_normalized_extra_not_raw_payload(self) -> None:
        uow, deps = self._build_uow()
        normalizer = _RecordingRelationExtraNormalizer()
        facade = self._write_facade_class()(uow=uow, extra_normalizer=normalizer)

        result = facade.update_relation_extra(
            relation_id="turnover_rel_1",
            payload={"note": "raw note", "unknown": "must not leak"},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
        )

        self.assertEqual(
            normalizer.calls,
            [
                {
                    "relation_id": "turnover_rel_1",
                    "payload": {"note": "raw note", "unknown": "must not leak"},
                    "actor_id": "finance-user",
                }
            ],
        )
        saved_extra = deps.extra_repository.extras[0]["extra"]
        self.assertEqual(saved_extra["note"], "normalized:raw note")
        self.assertEqual(saved_extra["updated_by"], "finance-user")
        self.assertNotIn("unknown", saved_extra)
        self.assertEqual(result["extra"], saved_extra)

    def test_relation_extra_write_facade_row_provider_receives_normalized_extra(self) -> None:
        uow, _deps = self._build_uow()
        normalizer = _RecordingRelationExtraNormalizer()
        row_provider = _RecordingRelationExtraRowProvider()
        facade = self._write_facade_class()(
            uow=uow,
            extra_normalizer=normalizer,
            row_provider=row_provider,
        )

        result = facade.update_relation_extra(
            relation_id="turnover_rel_1",
            payload={"note": "raw note"},
            actor_id="finance-user",
            tenant_id="default",
            scope_keys=["all"],
        )

        self.assertEqual(row_provider.calls[0]["extra"]["note"], "normalized:raw note")
        self.assertEqual(result["row"]["note"], "normalized:raw note")

    def test_relation_extra_write_facade_normalization_error_prevents_save_and_outbox(self) -> None:
        uow, deps = self._build_uow()
        facade = self._write_facade_class()(
            uow=uow,
            extra_normalizer=_RecordingRelationExtraNormalizer(fail=True),
        )

        with self.assertRaisesRegex(ValueError, "invalid normalized extra"):
            facade.update_relation_extra(
                relation_id="turnover_rel_1",
                payload={"note": "invalid"},
                actor_id="finance-user",
                tenant_id="default",
                scope_keys=["all"],
            )

        self.assertEqual(deps.connection.opened, 0)
        self.assertEqual(deps.extra_repository.extras, [])
        self.assertEqual(deps.dirty_outbox_writer.calls, [])

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

    def test_tag_selection_settings_adapter_saves_snapshot_and_audit_with_supplied_transaction(self) -> None:
        adapter_class = getattr(self._write_adapters_module(), "TurnoverLedgerTagSelectionSettingsAdapter")
        factory = _RecordingSettingsRepositoryFactory()
        transaction = _RecordingTransaction()
        adapter = adapter_class(repository_factory=factory)

        adapter.save_tag_selection_settings(
            next_snapshot={"turnover_ledger_tag_selection": {"version": 2}},
            audit_event={"actor_id": "finance-user", "new_version": 2},
            transaction=transaction,
        )

        self.assertEqual(factory.transactions, [transaction])
        self.assertEqual(
            factory.repositories[0].saved_settings,
            [{"turnover_ledger_tag_selection": {"version": 2}}],
        )
        self.assertEqual(factory.repositories[0].audit_events, [{"actor_id": "finance-user", "new_version": 2}])

    def test_tag_selection_settings_adapter_rejects_application_god_object(self) -> None:
        adapter_class = getattr(self._write_adapters_module(), "TurnoverLedgerTagSelectionSettingsAdapter")

        with self.assertRaises(TypeError):
            adapter_class(application=object())

    def test_postgres_bankdetail_port_adapter_rejects_application_god_object(self) -> None:
        # PF-P090 PostgreSQL Write Port Contract: bankdetail adapter must not receive Application.
        adapter_class = getattr(self._write_adapters_module(), "TurnoverLedgerBankdetailPortAdapter")

        with self.assertRaises(TypeError):
            adapter_class(application=object())

    def test_postgres_bankdetail_port_adapter_applies_updates_with_supplied_transaction(self) -> None:
        # PF-P090 PostgreSQL Write Port Contract: category facts/audit must join the UoW transaction.
        adapter_class = getattr(self._write_adapters_module(), "TurnoverLedgerBankdetailPortAdapter")
        factory = _RecordingBankdetailRepositoryFactory()
        transaction = _RecordingTransaction()
        adapter = adapter_class(repository_factory=factory)
        updates = [{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}]

        result = adapter.apply_turnover_category_updates(
            updates,
            actor_id="finance-user",
            transaction=transaction,
        )

        self.assertEqual(factory.transactions, [transaction])
        self.assertEqual(
            factory.repositories[0].category_updates,
            [{"updates": updates, "actor_id": "finance-user"}],
        )
        self.assertEqual(result["updated_categories"][0]["transaction_id"], "bank_txn_1")
        self.assertTrue({"headers", "cookies", "response", "status_code", "auth"}.isdisjoint(result))

    def test_target_relation_write_port_rejects_application_god_object(self) -> None:
        # PF-P095 Repository Ownership: future relation write port must receive granular dependencies.
        port_class = getattr(self._write_adapters_module(), "TurnoverLedgerRelationWritePort")

        with self.assertRaises(TypeError):
            port_class(application=object())

    def test_target_relation_write_port_previews_closure_without_persistence_and_persists_legacy_commands(self) -> None:
        # PF-P095 Repository Ownership: service orchestration should leave server.py.
        port_class = getattr(self._write_adapters_module(), "TurnoverLedgerRelationWritePort")
        relation_service = _RecordingTurnoverRelationService()
        routes = _RecordingTurnoverRoutes(relation_service)
        persistence_factory = _RecordingTurnoverPersistenceRepositoryFactory()
        transaction = _RecordingTransaction()
        selected_row_requests: list[list[str]] = []

        def load_selected_rows(row_ids: list[str]) -> list[dict[str, object]]:
            selected_row_requests.append(list(row_ids))
            available = {"bank_txn_1": {"id": "bank_txn_1"}, "bank_txn_2": {"id": "bank_txn_2"}}
            return [available[row_id] for row_id in row_ids if row_id in available]

        port = port_class(
            relation_service=relation_service,
            routes=routes,
            bank_rows_by_ids_provider=load_selected_rows,
            persistence_repository_factory=persistence_factory,
        )

        preview_result = port.preview_zero_difference_closure(
            bank_row_ids=["bank_txn_1", "bank_txn_2"],
            actor_id="finance-user",
            note="canonical closure",
            transaction=transaction,
        )

        confirm_result = port.confirm_relation(
            bank_row_ids=["bank_txn_1", "bank_txn_2"],
            actor_id="finance-user",
            note="confirm through port",
            transaction=transaction,
        )
        withdraw_result = port.withdraw_relation(
            relation_id="turnover_rel_1",
            actor_id="finance-user",
            note="withdraw through port",
            transaction=transaction,
        )

        self.assertEqual(persistence_factory.transactions, [transaction, transaction])
        self.assertEqual(len(persistence_factory.repositories[0].saved_relation_changes), 1)
        self.assertEqual(len(persistence_factory.repositories[1].saved_relation_changes), 1)
        self.assertEqual(persistence_factory.repositories[0].saved_relations, [])
        self.assertEqual(persistence_factory.repositories[1].saved_relations, [])
        self.assertEqual(
            selected_row_requests,
            [["bank_txn_1", "bank_txn_2"], ["bank_txn_1", "bank_txn_2"]],
        )
        self.assertEqual(
            relation_service.refreshes,
            [
                [{"id": "bank_txn_1"}, {"id": "bank_txn_2"}],
                [{"id": "bank_txn_1"}, {"id": "bank_txn_2"}],
            ],
        )
        self.assertEqual(relation_service.rebuilds, [])
        self.assertEqual(routes.confirm_calls[0]["actor"], "finance-user")
        self.assertEqual(routes.withdraw_calls[0]["relation_id"], "turnover_rel_1")
        self.assertEqual(preview_result["closure"]["relation_id"], "turnover_rel_preview")
        self.assertEqual(confirm_result["relation"]["status"], "confirmed")
        self.assertEqual(withdraw_result["relation"]["status"], "withdrawn")
        self.assertTrue({"headers", "cookies", "response", "status_code", "auth"}.isdisjoint(confirm_result))
        self.assertTrue({"headers", "cookies", "response", "status_code", "auth"}.isdisjoint(withdraw_result))

    def test_target_relation_write_port_rejects_stale_matching_audit_event(self) -> None:
        port_class = getattr(self._write_adapters_module(), "TurnoverLedgerRelationWritePort")
        relation_service = _RecordingTurnoverRelationService()
        relation_service.append_audit(relation_id="turnover_rel_1", action="old_confirm")
        persistence_factory = _RecordingTurnoverPersistenceRepositoryFactory()
        port = port_class(
            relation_service=relation_service,
            routes=_RecordingTurnoverRoutes(),
            bank_rows_by_ids_provider=lambda row_ids: [{"id": row_id} for row_id in row_ids],
            persistence_repository_factory=persistence_factory,
        )

        with self.assertRaisesRegex(RuntimeError, "must append a matching audit event"):
            port.confirm_relation(
                bank_row_ids=["bank_txn_1", "bank_txn_2"],
                actor_id="finance-user",
                note="must not reuse old audit",
                transaction=_RecordingTransaction(),
            )

        self.assertEqual(persistence_factory.transactions, [])

    def test_target_bankdetail_write_port_rejects_application_god_object(self) -> None:
        # PF-P095 Repository Ownership: future bankdetail write port must receive granular dependencies.
        port_class = getattr(self._write_adapters_module(), "TurnoverLedgerBankdetailWritePort")

        with self.assertRaises(TypeError):
            port_class(application=object())

    def test_target_bankdetail_write_port_updates_category_rebuilds_relations_and_persists(self) -> None:
        # PF-P095 Repository Ownership: cross-module write orchestration should be an explicit port.
        port_class = getattr(self._write_adapters_module(), "TurnoverLedgerBankdetailWritePort")
        category_service = _RecordingBankTransactionCategoryService()
        relation_service = _RecordingTurnoverRelationService()
        persistence_factory = _RecordingTurnoverPersistenceRepositoryFactory()
        mutation_calls: list[dict[str, object]] = []
        mutation_writer = SimpleNamespace(
            persist_many=lambda **kwargs: mutation_calls.append(dict(kwargs))
            or {"changed": True, "affected_months": ["2026-02"]}
        )
        transaction = _RecordingTransaction()
        port = port_class(
            category_service=category_service,
            relation_service=relation_service,
            bank_rows_provider=lambda: [{"id": "bank_txn_1"}],
            persistence_repository_factory=persistence_factory,
            category_mutation_writer=mutation_writer,
        )
        updates = [{"transaction_id": "bank_txn_1", "category_code": "borrow_in"}]

        result = port.apply_turnover_category_updates(
            updates,
            actor_id="finance-user",
            transaction=transaction,
        )

        self.assertEqual(persistence_factory.transactions, [transaction])
        self.assertEqual(category_service.updates, [{"updates": updates, "actor": "finance-user"}])
        self.assertEqual(relation_service.rebuilds, [[{"id": "bank_txn_1"}]])
        self.assertEqual(len(persistence_factory.repositories[0].saved_categories), 0)
        self.assertEqual(mutation_calls[0]["mutations"][0]["mutation_type"], "turnover_update")
        self.assertIs(mutation_calls[0]["transaction"], transaction)
        self.assertEqual(len(persistence_factory.repositories[0].saved_relations), 1)
        self.assertEqual(result["updated_categories"], updates)
        self.assertTrue({"headers", "cookies", "response", "status_code", "auth"}.isdisjoint(result))

    def test_adapter_raised_exception_rolls_back_turnover_uow(self) -> None:
        # PF-P090 PostgreSQL Write Port Contract: adapter failures must not become best-effort success.
        uow, deps = self._build_uow(relation_repository=_FailingTurnoverRelationPort())  # type: ignore[arg-type]
        facade = self._write_facade_class()(uow=uow)

        with self.assertRaisesRegex(RuntimeError, "relation adapter unavailable"):
            facade.confirm_relation(
                bank_row_ids=["bank_txn_1", "bank_txn_2"],
                actor_id="finance-user",
                tenant_id="default",
                note="adapter failure",
                affected_months=["2026-02"],
            )

        self.assertEqual(deps.connection.commits, 0)
        self.assertEqual(deps.connection.rollbacks, 1)
        self.assertEqual(deps.dirty_outbox_writer.calls, [])

    def test_postgres_settings_repository_saves_app_settings_with_supplied_transaction(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.postgres_repositories.ops_tax_etc")
        repository_class = getattr(module, "PostgresOpsTaxEtcRepository")
        transaction = _RecordingTransaction()
        repository = repository_class(connection=SimpleNamespace())

        repository.save_app_settings_in_transaction(
            {"turnover_ledger_tag_selection": {"version": 2}},
            transaction=transaction,
        )

        self.assertEqual(len(transaction.executed), 1)
        call = transaction.executed[0]
        self.assertIn("app.app_settings", str(call["sql"]))
        self.assertEqual(call["params"][0], "app_settings")

    def test_turnover_dirty_outbox_writer_batches_all_scopes_in_one_transaction(self) -> None:
        module = self._write_adapters_module()
        writer_class = getattr(module, "TurnoverLedgerDirtyOutboxWriter")
        queue = _TransactionOnlyQueueRepository()
        transaction = _RecordingTransaction()
        writer = writer_class(queue_repository=queue, tenant_id="tenant-a", priority="high", trace_id="trace-1")

        events = writer.enqueue_refreshes(
            transaction=transaction,
            refreshes=[
                {
                    "scope_type": "turnover_ledger",
                    "scope_keys": ["all", "2026-05"],
                    "reason": "relation_extra_update",
                    "payload": {"action_name": "turnover_relation_extra_update", "actor_id": "finance-user"},
                }
            ],
        )

        self.assertEqual(events, queue.calls)
        self.assertEqual(len(queue.batch_calls), 1)
        self.assertIs(queue.batch_calls[0]["transaction"], transaction)
        self.assertEqual([call["transaction"] for call in queue.calls], [transaction, transaction])
        self.assertEqual([call["scope_key"] for call in queue.calls], ["all", "2026-05"])
        self.assertEqual([call["scope_type"] for call in queue.calls], ["turnover_ledger", "turnover_ledger"])
        self.assertEqual([call["reason"] for call in queue.calls], ["relation_extra_update", "relation_extra_update"])
        self.assertEqual([call["tenant_id"] for call in queue.calls], ["tenant-a", "tenant-a"])
        self.assertEqual([call["priority"] for call in queue.calls], ["high", "high"])
        self.assertEqual([call["trace_id"] for call in queue.calls], ["trace-1", "trace-1"])
        self.assertEqual(
            [call["metadata"] for call in queue.calls],
            [
                {"action_name": "turnover_relation_extra_update"},
                {"action_name": "turnover_relation_extra_update"},
            ],
        )

    def test_turnover_dirty_outbox_writer_rejects_non_transactional_queue(self) -> None:
        writer_class = getattr(self._write_adapters_module(), "TurnoverLedgerDirtyOutboxWriter")
        writer = writer_class(queue_repository=_NonTransactionalQueueRepository())

        with self.assertRaisesRegex(RuntimeError, "enqueue_read_model_refreshes_in_transaction"):
            writer.enqueue_refreshes(
                transaction=_RecordingTransaction(),
                refreshes=[
                    {
                        "scope_type": "turnover_ledger",
                        "scope_keys": ["all"],
                        "reason": "relation_extra_update",
                    }
                ],
            )

    def test_relation_extra_normalizer_adapter_reuses_service_rules_without_state_mutation(self) -> None:
        service = self._extra_service_class().from_snapshot(
            {
                "extras": [
                    {
                        "relation_id": "turnover_rel_1",
                        "interest_rate_type": "annual",
                        "interest_rate_value": "0.060000",
                        "interest_paid_amount": "10.00",
                        "note": "old",
                        "updated_at": "2026-06-01T00:00:00+00:00",
                        "updated_by": "creator",
                    }
                ]
            }
        )
        before_snapshot = service.snapshot()
        adapter = getattr(self._write_adapters_module(), "TurnoverLedgerExtraNormalizerAdapter")(extra_service=service)

        normalized = adapter(
            relation_id=" turnover_rel_1 ",
            payload={"note": " new ", "interest_paid_amount": "12.345"},
            actor_id=" editor ",
        )

        self.assertEqual(normalized["relation_id"], "turnover_rel_1")
        self.assertEqual(normalized["interest_rate_type"], "annual")
        self.assertEqual(normalized["interest_rate_value"], "0.060000")
        self.assertEqual(normalized["interest_paid_amount"], "12.35")
        self.assertEqual(normalized["note"], "new")
        self.assertEqual(normalized["updated_by"], "editor")
        self.assertEqual(service.snapshot(), before_snapshot)

    def test_relation_extra_normalizer_adapter_feeds_facade_normalized_save(self) -> None:
        service = self._extra_service_class().from_snapshot(None)
        adapter = getattr(self._write_adapters_module(), "TurnoverLedgerExtraNormalizerAdapter")(extra_service=service)
        uow, deps = self._build_uow()
        facade = self._write_facade_class()(uow=uow, extra_normalizer=adapter)

        result = facade.update_relation_extra(
            relation_id=" turnover_rel_1 ",
            payload={"interest_rate_type": "none", "interest_rate_value": "9.99", "note": " saved "},
            actor_id=" finance-user ",
            tenant_id="default",
            scope_keys=["all"],
        )

        saved_extra = deps.extra_repository.extras[0]["extra"]
        self.assertEqual(saved_extra["relation_id"], "turnover_rel_1")
        self.assertEqual(saved_extra["interest_rate_type"], "none")
        self.assertEqual(saved_extra["interest_rate_value"], "0.000000")
        self.assertEqual(saved_extra["note"], "saved")
        self.assertEqual(result["extra"], saved_extra)
        self.assertEqual(service.snapshot(), {"version": 1, "extras": []})

    def test_relation_extra_normalizer_adapter_rejects_application_god_object(self) -> None:
        adapter_class = getattr(self._write_adapters_module(), "TurnoverLedgerExtraNormalizerAdapter")

        with self.assertRaises(TypeError):
            adapter_class(application=object())
