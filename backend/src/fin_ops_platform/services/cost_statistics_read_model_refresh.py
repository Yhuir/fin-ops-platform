from __future__ import annotations

from typing import Any

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class CostStatisticsReadModelRefreshService:
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
        if event.event_type != "cost_statistics.read_model.refresh":
            raise ValueError(f"Unsupported cost statistics read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "cost_statistics").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "cost_statistics" or not scope_key:
            raise ValueError("Cost statistics refresh requires scope_type='cost_statistics' and scope_key.")

        if scope_key.endswith(":all"):
            result = self._handle_parent_scope(scope_key)
        else:
            result = self._handle_month_scope(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        payload.setdefault("scope_key", scope_key)

        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope) and payload.get("readiness_status") != "refreshing":
            complete_dirty_scope(tenant_id=event.tenant_id, scope_type=scope_type, scope_key=scope_key)
        return payload

    def _handle_month_scope(self, scope_key: str) -> dict[str, Any]:
        rebuild_month = getattr(self._projection_builder, "rebuild_cost_statistics_month_scope", None)
        if not callable(rebuild_month):
            rebuild_month = getattr(self._projection_builder, "rebuild_cost_statistics_read_model_scope", None)
        if not callable(rebuild_month):
            raise RuntimeError("Application does not expose rebuild_cost_statistics_month_scope.")
        result = rebuild_month(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        payload.setdefault("refresh_kind", "month")
        self._enqueue_parent_scope(scope_key)
        return payload

    def _handle_parent_scope(self, scope_key: str) -> dict[str, Any]:
        missing_shards = self._missing_or_stale_shards(scope_key)
        if missing_shards:
            enqueued_scope_keys = self._enqueue_scope_keys(missing_shards, reason="cost_statistics_all_shard")
            return {
                "scope_key": scope_key,
                "refresh_kind": "parent_waiting_for_shards",
                "readiness_status": "refreshing",
                "enqueued_scope_keys": enqueued_scope_keys,
                "source_shard_count": 0,
            }
        rebuild_parent = getattr(self._projection_builder, "rebuild_cost_statistics_parent_scope", None)
        if not callable(rebuild_parent):
            rebuild_parent = getattr(self._projection_builder, "rebuild_cost_statistics_read_model_scope", None)
        if not callable(rebuild_parent):
            raise RuntimeError("Application does not expose rebuild_cost_statistics_parent_scope.")
        result = rebuild_parent(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        payload.setdefault("refresh_kind", "parent")
        payload["readiness_status"] = "fresh"
        return payload

    def _missing_or_stale_shards(self, scope_key: str) -> list[str]:
        missing_or_stale = getattr(self._projection_builder, "missing_or_stale_cost_statistics_shards", None)
        if callable(missing_or_stale):
            return [str(item).strip() for item in list(missing_or_stale(scope_key) or []) if str(item).strip()]
        list_shards = getattr(self._projection_builder, "list_cost_statistics_scope_shards", None)
        if not callable(list_shards):
            return []
        return [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]

    def _enqueue_all_scope_shards(self, scope_key: str) -> list[str] | None:
        list_shards = getattr(self._projection_builder, "list_cost_statistics_scope_shards", None)
        if not callable(list_shards):
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        return self._enqueue_scope_keys(shard_keys, reason="cost_statistics_all_shard")

    def _enqueue_parent_scope(self, scope_key: str) -> None:
        project_scope = str(scope_key or "").split(":", 1)[0]
        if project_scope not in {"active", "all"}:
            return
        self._enqueue_scope_keys([f"{project_scope}:all"], reason="cost_statistics_shard_converged")

    def _enqueue_scope_keys(self, scope_keys: list[str], *, reason: str) -> list[str]:
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            return []
        enqueued: list[str] = []
        for scope_key in scope_keys:
            normalized_scope_key = str(scope_key or "").strip()
            if not normalized_scope_key:
                continue
            enqueue(scope_type="cost_statistics", scope_key=normalized_scope_key, reason=reason)
            enqueued.append(normalized_scope_key)
        return enqueued
