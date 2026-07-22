from __future__ import annotations

from inspect import signature
from typing import Any

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class WorkbenchReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for workbench read model refresh.")
        self._queue_repository = queue_repository
        self._projection_builder = projection_builder

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "workbench.read_model.refresh":
            raise ValueError(f"Unsupported workbench read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "workbench").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "workbench" or not scope_key:
            raise ValueError("Workbench read model refresh requires scope_type='workbench' and scope_key.")

        source_version = event.source_version or event.payload.get("source_version")
        if not self._event_source_version_is_current(
            event,
            scope_key=scope_key,
            source_version=source_version,
        ):
            return {
                "scope_key": scope_key,
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": source_version,
            }

        if scope_key == "all":
            payload = self._enqueue_all_scope_shards(event)
            self._complete_dirty_scope(event, scope_type=scope_type, scope_key=scope_key, source_version=source_version)
            return payload

        rebuild = getattr(self._projection_builder, "rebuild_workbench_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Projection builder does not expose rebuild_workbench_read_model_scope.")
        if "source_version" in signature(rebuild).parameters:
            result = rebuild(scope_key, source_version=source_version)
        else:
            result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        if payload.get("published") is not True:
            return payload
        if not self._event_source_version_is_current(
            event,
            scope_key=scope_key,
            source_version=source_version,
        ):
            payload["skipped"] = True
            payload["skip_reason"] = "stale_source_version_after_publish"
            return payload
        self._complete_dirty_scope(event, scope_type=scope_type, scope_key=scope_key, source_version=source_version)
        return payload

    def _enqueue_all_scope_shards(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        list_shards = getattr(self._projection_builder, "list_workbench_scope_shards", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            raise RuntimeError("Workbench all-scope fan-out requires shard discovery and a durable refresh queue.")
        shard_keys = [str(item).strip() for item in list(list_shards("all") or []) if str(item).strip()]
        event_priority = str(event.priority or "normal").strip() or "normal"
        metadata = event.payload.get("metadata")
        force_refresh = event.payload.get("force_refresh") is True or (
            isinstance(metadata, dict) and metadata.get("force_refresh") is True
        )
        enqueued_scope_keys = refresh_gateway.enqueue_many(
            "workbench",
            shard_keys,
            reason="workbench_all_shard",
            tenant_id=event.tenant_id,
            priority=event_priority,
            trace_id=event.trace_id,
            metadata={"force_refresh": True} if force_refresh else None,
        )
        return {
            "scope_key": "all",
            "enqueued_scope_keys": enqueued_scope_keys,
            "fan_out": True,
            "row_count": 0,
        }

    def _complete_dirty_scope(
        self,
        event: RuntimeQueueEvent,
        *,
        scope_type: str,
        scope_key: str,
        source_version: object,
    ) -> None:
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=scope_type,
                scope_key=scope_key,
                source_version=source_version,
            )

    def _event_source_version_is_current(
        self,
        event: RuntimeQueueEvent,
        *,
        scope_key: str,
        source_version: object,
    ) -> bool:
        is_current = getattr(self._queue_repository, "read_model_refresh_is_current", None)
        if not callable(is_current):
            return True
        return bool(
            is_current(
                tenant_id=event.tenant_id,
                scope_type="workbench",
                scope_key=scope_key,
                source_version=source_version,
            )
        )
