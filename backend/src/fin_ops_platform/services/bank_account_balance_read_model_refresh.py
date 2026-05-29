from __future__ import annotations

from typing import Any

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class BankAccountBalanceReadModelRefreshService:
    def __init__(self, *, projection_builder: Any, queue_repository: Any | None = None) -> None:
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "bank_account_balance.read_model.refresh":
            raise ValueError(f"Unsupported bank account balance read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "bank_account_balance" or scope_key != "all":
            raise ValueError("Bank account balance refresh requires scope_type='bank_account_balance' and scope_key='all'.")
        rebuild = getattr(self._projection_builder, "rebuild_bank_account_balance_read_model", None)
        if not callable(rebuild):
            raise RuntimeError("Projection builder does not expose rebuild_bank_account_balance_read_model.")
        result = rebuild(source_version=event.source_version or event.payload.get("source_version"))
        complete = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete):
            complete(
                scope_type="bank_account_balance",
                scope_key="all",
                tenant_id=event.tenant_id,
                source_version=event.source_version or event.payload.get("source_version"),
            )
        return result if isinstance(result, dict) else {"scope_key": "all"}
