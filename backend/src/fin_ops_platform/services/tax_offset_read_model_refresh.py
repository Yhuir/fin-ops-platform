from __future__ import annotations

from typing import Any

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class TaxOffsetReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "tax_offset.read_model.refresh":
            raise ValueError(f"Unsupported tax offset read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "tax_offset").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "tax_offset" or not scope_key:
            raise ValueError("Tax offset refresh requires scope_type='tax_offset' and scope_key.")

        if scope_key == "all":
            shard_result = self._enqueue_all_scope_shards(event, scope_key)
            if shard_result is not None:
                return shard_result

        rebuild = getattr(self._projection_builder, "rebuild_tax_offset_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Tax offset projection builder does not expose rebuild_tax_offset_read_model_scope.")
        result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}

        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type=scope_type, scope_key=scope_key)
        return payload

    def _enqueue_all_scope_shards(self, event: RuntimeQueueEvent, scope_key: str) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_tax_offset_scope_shards", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        enqueued_scope_keys = refresh_gateway.enqueue_many("tax_offset", shard_keys, reason="tax_offset_all_shard")
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type="tax_offset", scope_key=scope_key)
        return {"scope_key": scope_key, "enqueued_scope_keys": enqueued_scope_keys, "entry_count": 0}
