from __future__ import annotations

from typing import Any

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class SearchPendingReadModelRefreshService:
    def __init__(self, *, application: Any, queue_repository: Any | None = None) -> None:
        self._application = application
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if event.event_type == "search.read_model.refresh":
            if scope_type != "search" or not scope_key:
                raise ValueError("Search refresh requires scope_type='search' and scope_key.")
            rebuild = getattr(self._application, "rebuild_search_index_scope", None)
        elif event.event_type == "pending_invoice.read_model.refresh":
            if scope_type != "pending_invoice" or not scope_key:
                raise ValueError("Pending invoice refresh requires scope_type='pending_invoice' and scope_key.")
            rebuild = getattr(self._application, "rebuild_pending_invoice_read_model_scope", None)
        else:
            raise ValueError(f"Unsupported search/pending read model event type: {event.event_type}")
        if not callable(rebuild):
            raise RuntimeError(f"Application does not expose rebuild method for {scope_type}.")
        result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type=scope_type, scope_key=scope_key)
        return payload
