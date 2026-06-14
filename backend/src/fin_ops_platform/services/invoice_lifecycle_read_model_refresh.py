from __future__ import annotations

from typing import Any

from fin_ops_platform.services.invoice_lifecycle_read_facade import INVOICE_LIFECYCLE_SCOPE_TYPE
from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE = "invoice_lifecycle.read_model.refresh"


class InvoiceLifecycleReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        application: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for invoice lifecycle read model refresh.")
        if application is not None:
            raise ValueError("InvoiceLifecycleReadModelRefreshService does not accept Application fallback dependencies.")
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE:
            raise ValueError(f"Unsupported invoice lifecycle read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != INVOICE_LIFECYCLE_SCOPE_TYPE or not scope_key:
            raise ValueError("Invoice lifecycle refresh requires scope_type='invoice_lifecycle' and scope_key.")
        source_version = event.source_version or event.payload.get("source_version")
        if not self._event_source_version_is_current(event, scope_key=scope_key, source_version=source_version):
            return {
                "scope_key": scope_key,
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": source_version,
            }
        if _invoice_lifecycle_scope_requires_expansion(scope_key):
            shard_result = self._enqueue_scope_shards(event, scope_key=scope_key)
            if shard_result is not None:
                return shard_result
        rebuild = getattr(self._projection_builder, "rebuild_invoice_lifecycle_read_model_scope", None)
        if not callable(rebuild):
            raise RuntimeError("Projection builder does not expose rebuild_invoice_lifecycle_read_model_scope.")
        result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        if not self._event_source_version_is_current(event, scope_key=scope_key, source_version=source_version):
            return {
                "scope_key": scope_key,
                "skipped": True,
                "skip_reason": "stale_source_version_after_rebuild",
                "source_version": source_version,
            }
        self._complete_dirty_scope(event, scope_key=scope_key, source_version=source_version)
        return payload

    def _enqueue_scope_shards(self, event: RuntimeQueueEvent, *, scope_key: str) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, "list_invoice_lifecycle_scope_shards", None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        if not shard_keys:
            mark_empty = getattr(self._projection_builder, "mark_invoice_lifecycle_scope_empty", None)
            if callable(mark_empty):
                mark_empty(scope_key)
        enqueued_scope_keys = refresh_gateway.enqueue_many(
            INVOICE_LIFECYCLE_SCOPE_TYPE,
            shard_keys,
            reason="invoice_lifecycle_month_shard",
        )
        self._complete_dirty_scope(event, scope_key=scope_key, source_version=event.source_version or event.payload.get("source_version"))
        return {"scope_key": scope_key, "enqueued_scope_keys": enqueued_scope_keys, "row_count": 0}

    def _complete_dirty_scope(self, event: RuntimeQueueEvent, *, scope_key: str, source_version: object) -> None:
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=INVOICE_LIFECYCLE_SCOPE_TYPE,
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
                scope_type=INVOICE_LIFECYCLE_SCOPE_TYPE,
                scope_key=scope_key,
                source_version=source_version,
            )
        )


def _invoice_lifecycle_scope_requires_expansion(scope_key: str) -> bool:
    return not MONTH_SCOPE_RE.match(str(scope_key or "").strip())
