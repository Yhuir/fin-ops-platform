from __future__ import annotations

from typing import Any

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class TaxOffsetReadModelRefreshService:
    def __init__(self, *, application: Any, queue_repository: Any | None = None) -> None:
        self._application = application
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "tax_offset.read_model.refresh":
            raise ValueError(f"Unsupported tax offset read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "tax_offset").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "tax_offset" or not scope_key:
            raise ValueError("Tax offset refresh requires scope_type='tax_offset' and scope_key.")

        rebuild = getattr(self._application, "rebuild_tax_offset_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Application does not expose rebuild_tax_offset_read_model_scope.")
        result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}

        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type=scope_type, scope_key=scope_key)
        return payload
