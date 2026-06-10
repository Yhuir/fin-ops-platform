from __future__ import annotations

from typing import Any

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class SearchPendingReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        application: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for search/pending read model refresh.")
        if application is not None:
            raise ValueError("SearchPendingReadModelRefreshService does not accept Application fallback dependencies.")
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if event.event_type == "search.read_model.refresh":
            if scope_type != "search" or not scope_key:
                raise ValueError("Search refresh requires scope_type='search' and scope_key.")
            if scope_key == "all":
                shard_result = self._enqueue_search_scope_shards(event, scope_key)
                if shard_result is not None:
                    return shard_result
            rebuild = getattr(self._projection_builder, "rebuild_search_index_scope", None)
        elif event.event_type == "pending_invoice.read_model.refresh":
            if scope_type != "pending_invoice" or not scope_key:
                raise ValueError("Pending invoice refresh requires scope_type='pending_invoice' and scope_key.")
            if _pending_invoice_scope_requires_expansion(scope_key):
                shard_result = self._enqueue_pending_invoice_scope_shards(event, scope_key)
                if shard_result is not None:
                    return shard_result
            rebuild = getattr(self._projection_builder, "rebuild_pending_invoice_read_model_scope", None)
        else:
            raise ValueError(f"Unsupported search/pending read model event type: {event.event_type}")
        if not callable(rebuild):
            raise RuntimeError(f"Projection builder does not expose rebuild method for {scope_type}.")
        result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type=scope_type, scope_key=scope_key)
        return payload

    def _enqueue_search_scope_shards(self, event: RuntimeQueueEvent, scope_key: str) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_search_scope_shards", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        enqueued_scope_keys = refresh_gateway.enqueue_many("search", shard_keys, reason="search_all_shard")
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type="search", scope_key=scope_key)
        return {"scope_key": scope_key, "enqueued_scope_keys": enqueued_scope_keys, "row_count": 0}

    def _enqueue_pending_invoice_scope_shards(self, event: RuntimeQueueEvent, scope_key: str) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_pending_invoice_scope_shards", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        if not shard_keys:
            mark_empty = getattr(self._projection_builder, "mark_pending_invoice_scope_empty", None)
            if callable(mark_empty):
                mark_empty(scope_key)
        enqueued_scope_keys = refresh_gateway.enqueue_many("pending_invoice", shard_keys, reason="pending_invoice_month_shard")
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type="pending_invoice", scope_key=scope_key)
        return {"scope_key": scope_key, "enqueued_scope_keys": enqueued_scope_keys, "row_count": 0}


def _pending_invoice_scope_requires_expansion(scope_key: str) -> bool:
    parts = [part.strip() for part in str(scope_key or "").split(":")]
    if len(parts) < 3:
        return True
    month = parts[2]
    return not (len(month) == 7 and month[4] == "-" and month[5:7].isdigit())
