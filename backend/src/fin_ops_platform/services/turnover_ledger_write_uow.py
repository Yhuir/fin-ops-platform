from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.workbench_uow import (
    _idempotency_commit,
    _idempotency_record,
    _idempotency_request_for,
    _idempotency_reserve,
    _is_existing_reservation,
    _is_taken_over_expired_reservation,
    _raise_if_idempotency_failed,
    _raise_if_idempotency_in_progress,
    _raise_on_fingerprint_conflict,
    _replay_committed_idempotency_response,
    _transaction_bound_idempotency_store,
)


@dataclass(frozen=True)
class TurnoverLedgerWriteContext:
    command: Any
    transaction: Any
    relation_repository: Any
    extra_repository: Any
    settings_port: Any
    bankdetail_port: Any
    workbench_pair_port: Any


class TurnoverLedgerWriteUnitOfWork:
    def __init__(
        self,
        *,
        connection: Any,
        relation_repository: Any,
        extra_repository: Any,
        settings_port: Any,
        bankdetail_port: Any,
        stale_precondition_port: Any,
        idempotency_store: Any | None = None,
        workbench_pair_port: Any | None = None,
    ) -> None:
        self._connection = connection
        self._relation_repository = relation_repository
        self._extra_repository = extra_repository
        self._settings_port = settings_port
        self._bankdetail_port = bankdetail_port
        self._stale_precondition_port = stale_precondition_port
        self._idempotency_store = idempotency_store
        self._workbench_pair_port = workbench_pair_port

    def run(self, command: Any, handler: Callable[[TurnoverLedgerWriteContext], Any]) -> Any:
        try:
            result = self._run_transaction(command, handler)
        except Exception:
            rollback_in_memory = getattr(self._bankdetail_port, "rollback_in_memory", None)
            if callable(rollback_in_memory):
                rollback_in_memory()
            raise
        commit_in_memory = getattr(self._bankdetail_port, "commit_in_memory", None)
        if callable(commit_in_memory):
            commit_in_memory()
        return result

    def _run_transaction(self, command: Any, handler: Callable[[TurnoverLedgerWriteContext], Any]) -> Any:
        idempotency = _idempotency_request_for(command) if self._idempotency_store is not None else None
        with self._connection.transaction() as transaction:
            idempotency_store = (
                _transaction_bound_idempotency_store(self._idempotency_store, transaction)
                if self._idempotency_store is not None
                else None
            )
            if idempotency is not None and idempotency_store is not None:
                reserved = _idempotency_reserve(idempotency_store, idempotency)
                if reserved is not None:
                    reserved_record = _idempotency_record(reserved)
                    _raise_on_fingerprint_conflict(reserved_record, idempotency)
                    _raise_if_idempotency_failed(reserved_record, idempotency)
                    replayed = _replay_committed_idempotency_response(reserved_record)
                    if replayed is not None:
                        return replayed
                    if _is_existing_reservation(reserved) and not _is_taken_over_expired_reservation(reserved):
                        _raise_if_idempotency_in_progress(reserved_record, idempotency)

            expected_versions = dict(getattr(command, "expected_versions", {}) or {})
            if expected_versions:
                self._stale_precondition_port.assert_current(
                    expected_versions=expected_versions,
                    transaction=transaction,
                )

            context = TurnoverLedgerWriteContext(
                command=command,
                transaction=transaction,
                relation_repository=self._relation_repository,
                extra_repository=self._extra_repository,
                settings_port=self._settings_port,
                bankdetail_port=self._bankdetail_port,
                workbench_pair_port=self._workbench_pair_port,
            )
            result = handler(context)
            if idempotency is not None and idempotency_store is not None:
                if not isinstance(result, dict):
                    raise TypeError("TurnoverLedgerWriteUnitOfWork idempotent handler must return a dict result.")
                result = dict(result)
                result["source_versions"] = {}
                result["outbox_event_ids"] = []
                _idempotency_commit(
                    idempotency_store,
                    idempotency,
                    result,
                    source_versions={},
                    outbox_event_ids=[],
                )
            return result
