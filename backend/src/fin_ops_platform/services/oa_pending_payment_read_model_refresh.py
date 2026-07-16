from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


OA_PENDING_PAYMENT_REFRESH_EVENT_TYPE = "oa_pending_payment.read_model.refresh"


class OaPendingPaymentReadModelRefreshService:
    def __init__(self, *, projection_builder: Any, queue_repository: Any) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for OA pending payment refresh.")
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if event.event_type != OA_PENDING_PAYMENT_REFRESH_EVENT_TYPE:
            raise ValueError(f"Unsupported OA pending payment read model event type: {event.event_type}")
        if scope_type != "oa_pending_payment" or not scope_key:
            raise ValueError("OA pending payment refresh requires scope_type='oa_pending_payment' and scope_key.")
        source_version = _source_version(event)
        if not self._is_current(event, scope_key=scope_key, source_version=source_version):
            return {
                "scope_key": scope_key,
                "source_version": source_version,
                "skipped": True,
                "skip_reason": "stale_source_version",
            }
        force_refresh = _force_refresh(event)
        if not MONTH_SCOPE_RE.match(scope_key):
            return self._fan_out_parent(
                event,
                scope_key=scope_key,
                source_version=source_version,
                force_refresh=force_refresh,
            )
        result = self._projection_builder.rebuild_scope(
            scope_key,
            tenant_id=event.tenant_id,
            source_version=source_version,
            force_refresh=force_refresh,
        )
        payload = dict(result) if isinstance(result, dict) else {"scope_key": scope_key}
        if payload.get("published") is False:
            return payload
        self._complete(event, scope_key=scope_key, source_version=source_version)
        return payload

    def _fan_out_parent(
        self,
        event: RuntimeQueueEvent,
        *,
        scope_key: str,
        source_version: int,
        force_refresh: bool,
    ) -> dict[str, Any]:
        list_shards = getattr(self._projection_builder, "list_scope_shards", None)
        if not callable(list_shards):
            raise RuntimeError("OA pending payment projector must expose list_scope_shards().")
        shard_keys = sorted(
            {
                str(item or "").strip()
                for item in list(list_shards(scope_key) or [])
                if MONTH_SCOPE_RE.match(str(item or "").strip())
            }
        )
        prune = getattr(self._projection_builder, "prune_scope_shards", None)
        if callable(prune):
            prune(shard_keys)
        gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not gateway.can_enqueue():
            raise RuntimeError("OA pending payment refresh gateway is unavailable.")
        enqueued = gateway.enqueue_many(
            "oa_pending_payment",
            shard_keys,
            reason="oa_pending_payment_month_shard",
            metadata={"force_refresh": True} if force_refresh else None,
        )
        self._complete(event, scope_key=scope_key, source_version=source_version)
        return {
            "scope_key": scope_key,
            "source_version": source_version,
            "enqueued_scope_keys": enqueued,
            "row_count": 0,
        }

    def _is_current(self, event: RuntimeQueueEvent, *, scope_key: str, source_version: int) -> bool:
        is_current = getattr(self._queue_repository, "read_model_refresh_is_current", None)
        if not callable(is_current):
            raise RuntimeError("queue_repository must expose read_model_refresh_is_current().")
        return bool(
            is_current(
                tenant_id=event.tenant_id,
                scope_type="oa_pending_payment",
                scope_key=scope_key,
                source_version=source_version,
            )
        )

    def _complete(self, event: RuntimeQueueEvent, *, scope_key: str, source_version: int) -> None:
        complete = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if not callable(complete):
            raise RuntimeError("queue_repository must expose complete_read_model_refresh().")
        complete(
            tenant_id=event.tenant_id,
            scope_type="oa_pending_payment",
            scope_key=scope_key,
            source_version=source_version,
        )


def _source_version(event: RuntimeQueueEvent) -> int:
    raw = event.source_version if event.source_version is not None else event.payload.get("source_version")
    if isinstance(raw, bool):
        raise ValueError("OA pending payment refresh source_version must be a non-negative integer.")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("OA pending payment refresh source_version must be a non-negative integer.") from exc
    if value < 0:
        raise ValueError("OA pending payment refresh source_version must be a non-negative integer.")
    return value


def _force_refresh(event: RuntimeQueueEvent) -> bool:
    if event.payload.get("force_refresh") is True:
        return True
    metadata = event.payload.get("metadata")
    return isinstance(metadata, dict) and metadata.get("force_refresh") is True
