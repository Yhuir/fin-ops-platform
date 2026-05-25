from __future__ import annotations

from inspect import signature
from typing import Any

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class BankDetailReadModelRefreshService:
    def __init__(self, *, projection_builder: Any, queue_repository: Any | None = None) -> None:
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "bank_detail.read_model.refresh":
            raise ValueError(f"Unsupported bank detail read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "bank_detail" or not scope_key:
            raise ValueError("Bank detail refresh requires scope_type='bank_detail' and scope_key.")
        source_version = event.source_version or event.payload.get("source_version")

        if scope_key == "all":
            shard_result = self._enqueue_all_scope_shards(event, source_version=source_version)
            if shard_result is not None:
                return shard_result

        rebuild = getattr(self._projection_builder, "rebuild_bank_detail_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Projection builder does not expose rebuild_bank_detail_read_model_scope.")
        if "source_version" in signature(rebuild).parameters:
            result = rebuild(scope_key, source_version=source_version)
        else:
            result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        self._complete_dirty_scope(event, scope_key=scope_key, source_version=source_version)
        return payload

    def _enqueue_all_scope_shards(self, event: RuntimeQueueEvent, *, source_version: Any) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_bank_detail_scope_shards", None)
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(list_shards) or not callable(enqueue):
            return None
        shard_keys = [str(item).strip() for item in list(list_shards("all") or []) if str(item).strip()]
        for shard_key in shard_keys:
            enqueue(scope_type="bank_detail", scope_key=shard_key, reason="bank_detail_all_shard")
        self._complete_dirty_scope(event, scope_key="all", source_version=source_version)
        return {"scope_key": "all", "enqueued_scope_keys": shard_keys, "row_count": 0}

    def _complete_dirty_scope(self, event: RuntimeQueueEvent, *, scope_key: str, source_version: Any) -> None:
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type="bank_detail",
                scope_key=scope_key,
                source_version=source_version,
            )
