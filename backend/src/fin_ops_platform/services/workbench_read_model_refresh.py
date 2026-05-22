from __future__ import annotations

from inspect import signature
from typing import Any

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class WorkbenchReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        application: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        self._projection_builder = projection_builder if projection_builder is not None else application
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "workbench.read_model.refresh":
            raise ValueError(f"Unsupported workbench read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "workbench").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "workbench" or not scope_key:
            raise ValueError("Workbench read model refresh requires scope_type='workbench' and scope_key.")

        if scope_key == "all":
            shard_result = self._enqueue_all_scope_shards(event, scope_key)
            if shard_result is not None:
                return shard_result

        rebuild = getattr(self._projection_builder, "rebuild_workbench_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Application does not expose rebuild_workbench_read_model_scope.")
        source_version = event.payload.get("source_version")
        if "source_version" in signature(rebuild).parameters:
            result = rebuild(scope_key, source_version=source_version)
        else:
            result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}

        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=scope_type,
                scope_key=scope_key,
                source_version=source_version,
            )
        return payload

    def _enqueue_all_scope_shards(self, event: RuntimeQueueEvent, scope_key: str) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_workbench_scope_shards", None)
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(list_shards) or not callable(enqueue):
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        for shard_key in shard_keys:
            enqueue(scope_type="workbench", scope_key=shard_key, reason="workbench_all_shard")
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type="workbench",
                scope_key=scope_key,
                source_version=event.source_version or event.payload.get("source_version"),
            )
        return {"scope_key": scope_key, "enqueued_scope_keys": shard_keys, "row_count": 0}
