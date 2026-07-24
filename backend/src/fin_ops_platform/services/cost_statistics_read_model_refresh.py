from __future__ import annotations

from typing import Any

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class CostStatisticsReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for cost statistics read model refresh.")
        if queue_repository is None:
            raise ValueError("queue_repository is required for cost statistics read model refresh.")
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "cost_statistics.read_model.refresh":
            raise ValueError(f"Unsupported cost statistics read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "cost_statistics").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "cost_statistics" or not scope_key:
            raise ValueError("Cost statistics refresh requires scope_type='cost_statistics' and scope_key.")
        source_version = _event_source_version(event)
        priority = str(event.priority or "normal").strip() or "normal"
        force_refresh = _event_force_refresh(event)

        if scope_key.endswith(":all"):
            result = self._handle_parent_scope(
                scope_key,
                tenant_id=event.tenant_id,
                source_version=source_version,
                priority=priority,
                trace_id=event.trace_id,
                force_refresh=force_refresh,
            )
        else:
            result = self._handle_month_scope(
                scope_key,
                tenant_id=event.tenant_id,
                source_version=source_version,
                force_refresh=force_refresh,
            )
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        payload.setdefault("scope_key", scope_key)
        payload.setdefault("source_version", source_version)

        if payload.get("readiness_status") == "refreshing":
            return payload
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if not callable(complete_dirty_scope):
            raise RuntimeError("queue_repository must expose complete_read_model_refresh.")
        completed = bool(
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=scope_type,
                scope_key=scope_key,
                source_version=source_version,
            )
        )
        if not completed:
            payload.update(
                {
                    "skipped": True,
                    "skip_reason": "stale_source_version_after_rebuild",
                    "readiness_status": "refreshing",
                }
            )
            return payload
        if not scope_key.endswith(":all"):
            self._enqueue_parent_scope(
                scope_key,
                tenant_id=event.tenant_id,
                priority=priority,
                trace_id=event.trace_id or event.event_id,
            )
        return payload

    def _handle_month_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        force_refresh: bool,
    ) -> dict[str, Any]:
        rebuild_month = getattr(self._projection_builder, "rebuild_cost_statistics_month_scope", None)
        if not callable(rebuild_month):
            raise RuntimeError("Projection builder does not expose rebuild_cost_statistics_month_scope.")
        rebuild_kwargs: dict[str, object] = {
            "tenant_id": tenant_id,
            "source_version": source_version,
        }
        if force_refresh:
            rebuild_kwargs["force_refresh"] = True
        result = rebuild_month(scope_key, **rebuild_kwargs)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        payload.setdefault("refresh_kind", "month")
        if payload.get("published") is False:
            payload["readiness_status"] = "refreshing"
            return payload
        return payload

    def _handle_parent_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        priority: str,
        trace_id: str | None,
        force_refresh: bool,
    ) -> dict[str, Any]:
        pending_shards = self._all_shards(scope_key) if force_refresh else []
        if pending_shards:
            enqueued_scope_keys = self._enqueue_scope_keys(
                pending_shards,
                reason="cost_statistics_all_shard",
                tenant_id=tenant_id,
                priority=priority,
                trace_id=trace_id,
                force_refresh=force_refresh,
            )
            return {
                "scope_key": scope_key,
                "refresh_kind": "parent_waiting_for_shards",
                "readiness_status": "refreshing",
                "enqueued_scope_keys": enqueued_scope_keys,
                "source_shard_count": 0,
                "source_version": source_version,
            }
        rebuild_parent = getattr(self._projection_builder, "rebuild_cost_statistics_parent_scope", None)
        if not callable(rebuild_parent):
            raise RuntimeError("Projection builder does not expose rebuild_cost_statistics_parent_scope.")
        rebuild_kwargs: dict[str, object] = {
            "tenant_id": tenant_id,
            "source_version": source_version,
        }
        if force_refresh:
            rebuild_kwargs["force_refresh"] = True
        result = rebuild_parent(scope_key, **rebuild_kwargs)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        payload.setdefault("refresh_kind", "parent")
        payload["readiness_status"] = "refreshing" if payload.get("published") is False else "fresh"
        return payload

    def _all_shards(self, scope_key: str) -> list[str]:
        list_shards = getattr(self._projection_builder, "list_cost_statistics_scope_shards", None)
        if not callable(list_shards):
            raise RuntimeError("Projection builder does not expose list_cost_statistics_scope_shards.")
        return [
            str(item).strip()
            for item in list(list_shards(scope_key) or [])
            if str(item).strip()
        ]

    def _enqueue_parent_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        priority: str,
        trace_id: str | None,
    ) -> None:
        project_scope = str(scope_key or "").split(":", 1)[0]
        if project_scope not in {"active", "all"}:
            return
        self._enqueue_scope_keys(
            [f"{project_scope}:all"],
            reason="cost_statistics_shard_converged",
            tenant_id=tenant_id,
            priority=priority,
            trace_id=trace_id,
        )

    def _enqueue_scope_keys(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        tenant_id: str,
        priority: str,
        trace_id: str | None,
        force_refresh: bool = False,
    ) -> list[str]:
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return []
        return refresh_gateway.enqueue_many(
            "cost_statistics",
            scope_keys,
            reason=reason,
            tenant_id=tenant_id,
            priority=priority,
            trace_id=trace_id,
            metadata={"force_refresh": True} if force_refresh else None,
        )


def _event_source_version(event: RuntimeQueueEvent) -> int:
    value = event.source_version if event.source_version is not None else event.payload.get("source_version")
    if isinstance(value, bool) or value in (None, ""):
        raise ValueError("Cost statistics refresh requires a non-negative integer source_version.")
    try:
        source_version = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Cost statistics refresh requires a non-negative integer source_version.") from exc
    if source_version < 0 or str(value).strip() != str(source_version):
        raise ValueError("Cost statistics refresh requires a non-negative integer source_version.")
    return source_version


def _event_force_refresh(event: RuntimeQueueEvent) -> bool:
    if event.payload.get("force_refresh") is True:
        return True
    metadata = event.payload.get("metadata")
    return isinstance(metadata, dict) and metadata.get("force_refresh") is True
