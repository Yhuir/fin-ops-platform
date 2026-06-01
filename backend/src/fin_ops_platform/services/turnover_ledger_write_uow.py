from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TurnoverLedgerWriteContext:
    command: Any
    transaction: Any
    relation_repository: Any
    extra_repository: Any
    settings_port: Any
    bankdetail_port: Any


class TurnoverLedgerWriteUnitOfWork:
    def __init__(
        self,
        *,
        connection: Any,
        relation_repository: Any,
        extra_repository: Any,
        settings_port: Any,
        bankdetail_port: Any,
        dirty_outbox_writer: Any,
        stale_precondition_port: Any,
    ) -> None:
        self._connection = connection
        self._relation_repository = relation_repository
        self._extra_repository = extra_repository
        self._settings_port = settings_port
        self._bankdetail_port = bankdetail_port
        self._dirty_outbox_writer = dirty_outbox_writer
        self._stale_precondition_port = stale_precondition_port

    def run(self, command: Any, handler: Callable[[TurnoverLedgerWriteContext], Any]) -> Any:
        with self._connection.transaction() as transaction:
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
            )
            result = handler(context)
            self._dirty_outbox_writer.enqueue_refresh(
                transaction=transaction,
                scope_type="turnover_ledger",
                scope_keys=list(getattr(command, "scope_keys", []) or ["all"]),
                reason=str(getattr(command, "action_name", "") or "turnover_ledger_write"),
                payload={
                    "tenant_id": getattr(command, "tenant_id", None),
                    "actor_id": getattr(command, "actor_id", None),
                    "action_name": getattr(command, "action_name", None),
                },
            )
            return result
