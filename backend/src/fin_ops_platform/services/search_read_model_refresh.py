from __future__ import annotations

from typing import Any

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.search_read_model_refresh_producer import (
    SearchReadModelRefreshProducer,
)


SEARCH_REFRESH_EVENT_TYPE = "search.read_model.refresh"


class SearchReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any,
        queue_repository: Any | None = None,
        search_read_model_refresh_producer: Any | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for Search refresh.")
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository
        self._producer = (
            search_read_model_refresh_producer
            or SearchReadModelRefreshProducer(
                refresh_gateway_provider=lambda: ReadModelRefreshGateway(
                    queue_repository=self._queue_repository
                )
            )
        )

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(
            event.scope_key
            or event.payload.get("scope_key")
            or event.aggregate_id
            or ""
        ).strip()
        if event.event_type != SEARCH_REFRESH_EVENT_TYPE:
            raise ValueError(f"Unsupported Search read model event type: {event.event_type}")
        if scope_type != "search" or not scope_key:
            raise ValueError("Search refresh requires scope_type='search' and scope_key.")
        source_version = event.source_version or event.payload.get("source_version")
        if not self._is_current(
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
            shards = [
                str(item).strip()
                for item in list(
                    self._projection_builder.list_search_scope_shards("all") or []
                )
                if str(item).strip()
            ]
            enqueued = self._producer.enqueue_scope_keys(
                shards,
                reason="search_all_shard",
            )
            if enqueued:
                self._complete(event=event, scope_key=scope_key)
                return {
                    "scope_key": scope_key,
                    "enqueued_scope_keys": enqueued,
                    "row_count": 0,
                }
        result = self._projection_builder.rebuild_search_index_scope(scope_key)
        self._complete(event=event, scope_key=scope_key)
        return result if isinstance(result, dict) else {"scope_key": scope_key}

    def _is_current(
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
                scope_type="search",
                scope_key=scope_key,
                source_version=source_version,
            )
        )

    def _complete(self, *, event: RuntimeQueueEvent, scope_key: str) -> None:
        complete = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete):
            complete(
                tenant_id=event.tenant_id,
                scope_type="search",
                scope_key=scope_key,
            )
