from __future__ import annotations

from typing import Any

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


WORKBENCH_RELATION_REFRESH_EVENT_TYPE = "workbench_relation.read_model.refresh"
WORKBENCH_RELATION_SCOPE_TYPE = "workbench_relation"


class WorkbenchRelationReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        application: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for workbench relation read model refresh.")
        if application is not None:
            raise ValueError("WorkbenchRelationReadModelRefreshService does not accept Application fallback dependencies.")
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != WORKBENCH_RELATION_REFRESH_EVENT_TYPE:
            raise ValueError(f"Unsupported workbench relation read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != WORKBENCH_RELATION_SCOPE_TYPE or not scope_key:
            raise ValueError("Workbench relation refresh requires scope_type='workbench_relation' and scope_key.")
        if scope_key == "all":
            shard_result = self._enqueue_scope_shards(event, scope_key)
            if shard_result is not None:
                return shard_result
        row_ids = _event_text_list(event.payload, "row_ids")
        if not row_ids:
            metadata = event.payload.get("metadata")
            row_ids = _event_text_list(metadata if isinstance(metadata, dict) else {}, "row_ids")
        if row_ids:
            rebuild_rows = getattr(self._projection_builder, "rebuild_workbench_relation_read_model_rows", None)
            if callable(rebuild_rows):
                result = rebuild_rows(scope_key, row_ids=row_ids)
                payload = result if isinstance(result, dict) else {"scope_key": scope_key}
                complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
                if callable(complete_dirty_scope):
                    complete_dirty_scope(tenant_id=event.tenant_id, scope_type=scope_type, scope_key=scope_key)
                return payload
        rebuild = getattr(self._projection_builder, "rebuild_workbench_relation_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Projection builder does not expose rebuild_workbench_relation_read_model_scope.")
        result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type=scope_type, scope_key=scope_key)
        return payload

    def _enqueue_scope_shards(self, event: RuntimeQueueEvent, scope_key: str) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_workbench_relation_scope_shards", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        if not shard_keys:
            mark_empty = getattr(self._projection_builder, "mark_workbench_relation_scope_empty", None)
            if callable(mark_empty):
                mark_empty(scope_key)
        enqueued_scope_keys = refresh_gateway.enqueue_many(
            WORKBENCH_RELATION_SCOPE_TYPE,
            shard_keys,
            reason="workbench_relation_month_shard",
        )
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type=WORKBENCH_RELATION_SCOPE_TYPE, scope_key=scope_key)
        return {"scope_key": scope_key, "enqueued_scope_keys": enqueued_scope_keys, "row_count": 0}


def _event_text_list(payload: dict[str, Any], name: str) -> list[str]:
    raw_value = payload.get(name) if isinstance(payload, dict) else None
    if isinstance(raw_value, str):
        raw_items: list[object] = [raw_value]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_items = list(raw_value)
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
