from __future__ import annotations

from inspect import signature
from typing import Any, Callable

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


WORKBENCH_SHARD_AGGREGATE_DELAY_SECONDS = 3.0
WORKBENCH_HOT_SHARD_AGGREGATE_DELAY_SECONDS = 0.0


class WorkbenchReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        queue_repository: Any | None = None,
        post_refresh_warmer: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for workbench read model refresh.")
        self._queue_repository = queue_repository
        self._projection_builder = projection_builder
        self._post_refresh_warmer = post_refresh_warmer

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != "workbench.read_model.refresh":
            raise ValueError(f"Unsupported workbench read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "workbench").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != "workbench" or not scope_key:
            raise ValueError("Workbench read model refresh requires scope_type='workbench' and scope_key.")

        source_version = event.source_version or event.payload.get("source_version")
        aggregate_only = scope_key == "all" and _truthy(event.payload.get("aggregate_only"))
        parent_scope_keys = event.payload.get("parent_scope_keys")
        aggregate_from_parent_shards = aggregate_only and isinstance(parent_scope_keys, list) and bool(parent_scope_keys)
        if aggregate_from_parent_shards:
            active_parent_scope_keys = self._active_parent_scope_keys(event.tenant_id, parent_scope_keys)
            if active_parent_scope_keys:
                raise RuntimeError(
                    "workbench_read_model_not_fresh: "
                    f"parent_scope_keys={','.join(active_parent_scope_keys)}"
                )
            stale_parent_scope_keys = self._stale_parent_scope_keys(event.tenant_id, parent_scope_keys)
            if stale_parent_scope_keys:
                raise RuntimeError(
                    "workbench_read_model_not_fresh: "
                    f"parent_scope_keys={','.join(stale_parent_scope_keys)}"
                )
        if not aggregate_from_parent_shards and not self._event_source_version_is_current(
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

        if scope_key == "all" and not aggregate_only:
            shard_result = self._enqueue_all_scope_shards(event, scope_key)
            if shard_result is not None:
                return shard_result

        if aggregate_only:
            rebuild = getattr(self._projection_builder, "refresh_workbench_all_scope_from_active_shards", None)
        else:
            rebuild = getattr(self._projection_builder, "rebuild_workbench_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Projection builder does not expose rebuild_workbench_read_model_scope.")
        if "source_version" in signature(rebuild).parameters:
            result = rebuild(scope_key, source_version=source_version)
        else:
            result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        if aggregate_only and not _all_scope_aggregate_published(payload):
            raise RuntimeError(
                "workbench_all_scope_aggregate_not_published: "
                f"scope_key={scope_key} status={payload.get('read_model_status')!r} "
                f"active_generation_id={payload.get('active_generation_id')!r}"
            )

        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=scope_type,
                scope_key=scope_key,
                source_version=source_version,
            )
        aggregate_enqueued = self._enqueue_all_scope_aggregate_after_shard_publish(event, scope_key)
        if aggregate_enqueued is not None:
            payload["aggregate_enqueued"] = aggregate_enqueued
        warmup_payload = self._warm_after_publish(scope_key)
        if warmup_payload is not None:
            payload["cache_warmup"] = warmup_payload
        return payload

    def _enqueue_all_scope_shards(self, event: RuntimeQueueEvent, scope_key: str) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_workbench_scope_shards", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        event_priority = str(event.priority or "normal").strip() or "normal"
        enqueued_scope_keys = refresh_gateway.enqueue_many(
            "workbench",
            shard_keys,
            reason="workbench_all_shard",
            priority=event_priority,
            trace_id=event.trace_id,
        )
        enqueue_event = getattr(self._queue_repository, "enqueue", None)
        enqueue_aggregate = getattr(self._queue_repository, "enqueue_workbench_all_aggregate_refresh", None)
        can_enqueue_aggregate = callable(enqueue_aggregate) or callable(enqueue_event)
        if can_enqueue_aggregate:
            source_version = event.source_version or event.payload.get("source_version")
            if callable(enqueue_aggregate):
                enqueue_aggregate(
                    tenant_id=event.tenant_id,
                    parent_scope_keys=enqueued_scope_keys,
                    source_version=source_version,
                    reason=str(event.payload.get("reason") or "workbench_all_shard"),
                    priority=event_priority,
                    trace_id=event.trace_id,
                )
            else:
                enqueue_event(
                    event_type="workbench.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="all",
                    scope_type="workbench",
                    scope_key=scope_key,
                    dedupe_key=f"workbench.read_model.refresh:workbench:all:aggregate:{source_version or 'latest'}",
                    payload={
                        "scope_type": "workbench",
                        "scope_key": scope_key,
                        "aggregate_only": True,
                        "source_version": source_version,
                        "parent_scope_keys": enqueued_scope_keys,
                    },
                    tenant_id=event.tenant_id,
                    source_version=source_version,
                    priority=event_priority,
                    trace_id=event.trace_id,
                )
        return {
            "scope_key": scope_key,
            "enqueued_scope_keys": enqueued_scope_keys,
            "aggregate_enqueued": can_enqueue_aggregate,
            "row_count": 0,
        }

    def _enqueue_all_scope_aggregate_after_shard_publish(self, event: RuntimeQueueEvent, scope_key: str) -> bool | None:
        if scope_key == "all":
            return None
        enqueue_event = getattr(self._queue_repository, "enqueue", None)
        enqueue_aggregate = getattr(self._queue_repository, "enqueue_workbench_all_aggregate_refresh", None)
        if not callable(enqueue_aggregate) and not callable(enqueue_event):
            return None
        source_version = event.source_version or event.payload.get("source_version")
        aggregate_delay_seconds = _aggregate_delay_seconds_for(event)
        aggregate_priority = _aggregate_priority_for(event, aggregate_delay_seconds)
        if callable(enqueue_aggregate):
            enqueue_aggregate(
                tenant_id=event.tenant_id,
                parent_scope_keys=[scope_key],
                source_version=source_version,
                reason=str(event.payload.get("reason") or "workbench_shard_published"),
                priority=aggregate_priority,
                delay_seconds=aggregate_delay_seconds,
                trace_id=event.trace_id,
            )
        else:
            enqueue_event(
                event_type="workbench.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="all",
                scope_type="workbench",
                scope_key="all",
                dedupe_key=f"workbench.read_model.refresh:workbench:all:aggregate:{source_version or 'latest'}",
                payload={
                    "scope_type": "workbench",
                    "scope_key": "all",
                    "aggregate_only": True,
                    "source_version": source_version,
                    "parent_scope_keys": [scope_key],
                },
                tenant_id=event.tenant_id,
                source_version=source_version,
                priority=aggregate_priority,
                trace_id=event.trace_id,
            )
        return True

    def _warm_after_publish(self, scope_key: str) -> dict[str, Any] | None:
        if self._post_refresh_warmer is None:
            return None
        try:
            result = self._post_refresh_warmer(scope_key)
        except Exception as error:
            return {"status": "failed", "error": str(error) or error.__class__.__name__}
        return result if isinstance(result, dict) else None

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

    def _active_parent_scope_keys(self, tenant_id: str, parent_scope_keys: list[Any]) -> list[str]:
        is_active = getattr(self._queue_repository, "read_model_refresh_is_active", None)
        if not callable(is_active):
            return []
        active_scope_keys: list[str] = []
        for scope_key in _normalized_parent_scope_keys(parent_scope_keys):
            if is_active(tenant_id=tenant_id, scope_type="workbench", scope_key=scope_key):
                active_scope_keys.append(scope_key)
        return active_scope_keys

    def _stale_parent_scope_keys(self, tenant_id: str, parent_scope_keys: list[Any]) -> list[str]:
        is_fresh = getattr(self._queue_repository, "read_model_refresh_is_fresh", None)
        if not callable(is_fresh):
            return []
        stale_scope_keys: list[str] = []
        for scope_key in _normalized_parent_scope_keys(parent_scope_keys):
            if not is_fresh(tenant_id=tenant_id, scope_type="workbench", scope_key=scope_key):
                stale_scope_keys.append(scope_key)
        return stale_scope_keys


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _aggregate_delay_seconds_for(event: RuntimeQueueEvent) -> float:
    if _is_workbench_relation_write_refresh(event):
        return WORKBENCH_HOT_SHARD_AGGREGATE_DELAY_SECONDS
    priority = str(event.priority or "").strip().lower()
    if priority in {"urgent", "high"}:
        return WORKBENCH_HOT_SHARD_AGGREGATE_DELAY_SECONDS
    return WORKBENCH_SHARD_AGGREGATE_DELAY_SECONDS


def _aggregate_priority_for(event: RuntimeQueueEvent, delay_seconds: float) -> str:
    if delay_seconds <= 0:
        priority = str(event.priority or "normal").strip().lower()
        return priority if priority in {"urgent", "high"} else "high"
    return "low"


def _is_workbench_relation_write_refresh(event: RuntimeQueueEvent) -> bool:
    reason = str(event.payload.get("reason") or "").strip()
    if reason == "workbench_relation_changed":
        return True
    action_name = str(event.payload.get("action_name") or "").strip()
    if action_name in {"confirm_link", "cancel_link", "withdraw_link"}:
        return True
    metadata = event.payload.get("metadata")
    if isinstance(metadata, dict):
        metadata_action = str(metadata.get("action_name") or "").strip()
        return metadata_action in {"confirm_link", "cancel_link", "withdraw_link"}
    return False


def _normalized_parent_scope_keys(parent_scope_keys: list[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in parent_scope_keys:
        scope_key = str(item or "").strip()
        if not scope_key or scope_key in seen:
            continue
        seen.add(scope_key)
        normalized.append(scope_key)
    return normalized


def _all_scope_aggregate_published(payload: dict[str, Any]) -> bool:
    if _truthy(payload.get("aggregate_published")):
        return True
    active_generation_id = str(payload.get("active_generation_id") or "").strip()
    if not active_generation_id:
        return False
    read_model_status = str(payload.get("read_model_status") or "fresh").strip().lower()
    return read_model_status == "fresh"
