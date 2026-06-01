from __future__ import annotations

from inspect import signature
from typing import Any

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.turnover_ledger_query_service import (
    TURNOVER_LEDGER_REFRESH_EVENT_TYPE,
    TURNOVER_LEDGER_SCOPE_TYPE,
)


class TurnoverLedgerReadModelRefreshService:
    def __init__(self, *, projection_builder: Any, queue_repository: Any | None = None) -> None:
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != TURNOVER_LEDGER_REFRESH_EVENT_TYPE:
            raise ValueError(f"Unsupported turnover ledger read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != TURNOVER_LEDGER_SCOPE_TYPE or not scope_key:
            raise ValueError("Turnover ledger refresh requires scope_type='turnover_ledger' and scope_key.")
        source_version = event.source_version or event.payload.get("source_version")
        rebuild = getattr(self._projection_builder, "rebuild_turnover_ledger_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Projection builder does not expose rebuild_turnover_ledger_read_model_scope.")
        if "source_version" in signature(rebuild).parameters:
            result = rebuild(scope_key, source_version=source_version)
        else:
            result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        self._complete_dirty_scope(event, scope_key=scope_key, source_version=source_version)
        return payload

    def _complete_dirty_scope(self, event: RuntimeQueueEvent, *, scope_key: str, source_version: Any) -> None:
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=TURNOVER_LEDGER_SCOPE_TYPE,
                scope_key=scope_key,
                source_version=source_version,
            )
