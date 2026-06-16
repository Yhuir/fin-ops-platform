from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class InvoiceUsageCollectionReadModelRefreshService:
    def __init__(
        self,
        *,
        projection_builder: Any | None = None,
        queue_repository: Any | None = None,
    ) -> None:
        if projection_builder is None:
            raise ValueError("projection_builder is required for invoice usage collection read model refresh.")
        self._projection_builder = projection_builder
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if event.event_type == "input_invoice_usage.read_model.refresh":
            if scope_type != "input_invoice_usage" or not scope_key:
                raise ValueError("Input invoice usage refresh requires scope_type='input_invoice_usage' and scope_key.")
            if _invoice_scope_requires_expansion(scope_key):
                shard_result = self._enqueue_scope_shards(
                    event,
                    scope_type=scope_type,
                    scope_key=scope_key,
                    list_method_name="list_input_invoice_usage_scope_shards",
                    empty_method_name="mark_input_invoice_usage_scope_empty",
                    shard_reason="input_invoice_usage_month_shard",
                )
                if shard_result is not None:
                    return shard_result
            rebuild = getattr(self._projection_builder, "rebuild_input_invoice_usage_read_model_scope", None)
        elif event.event_type == "output_invoice_collection.read_model.refresh":
            if scope_type != "output_invoice_collection" or not scope_key:
                raise ValueError("Output invoice collection refresh requires scope_type='output_invoice_collection' and scope_key.")
            if _invoice_scope_requires_expansion(scope_key):
                shard_result = self._enqueue_scope_shards(
                    event,
                    scope_type=scope_type,
                    scope_key=scope_key,
                    list_method_name="list_output_invoice_collection_scope_shards",
                    empty_method_name="mark_output_invoice_collection_scope_empty",
                    shard_reason="output_invoice_collection_month_shard",
                )
                if shard_result is not None:
                    return shard_result
            rebuild = getattr(self._projection_builder, "rebuild_output_invoice_collection_read_model_scope", None)
        elif event.event_type == "oa_pending_payment.read_model.refresh":
            if scope_type != "oa_pending_payment" or not scope_key:
                raise ValueError("OA pending payment refresh requires scope_type='oa_pending_payment' and scope_key.")
            if _invoice_scope_requires_expansion(scope_key):
                shard_result = self._enqueue_scope_shards(
                    event,
                    scope_type=scope_type,
                    scope_key=scope_key,
                    list_method_name="list_oa_pending_payment_scope_shards",
                    empty_method_name="mark_oa_pending_payment_scope_empty",
                    shard_reason="oa_pending_payment_month_shard",
                )
                if shard_result is not None:
                    return shard_result
            rebuild = getattr(self._projection_builder, "rebuild_oa_pending_payment_read_model_scope", None)
        else:
            raise ValueError(f"Unsupported invoice relation read model event type: {event.event_type}")
        if not callable(rebuild):
            raise RuntimeError(f"Projection builder does not expose rebuild method for {scope_type}.")
        result = rebuild(scope_key)
        payload = result if isinstance(result, dict) else {"scope_key": scope_key}
        self._complete_dirty_scope(event, scope_type=scope_type, scope_key=scope_key)
        return payload

    def _enqueue_scope_shards(
        self,
        event: RuntimeQueueEvent,
        *,
        scope_type: str,
        scope_key: str,
        list_method_name: str,
        empty_method_name: str,
        shard_reason: str,
    ) -> dict[str, Any] | None:
        list_shards = getattr(self._projection_builder, list_method_name, None)
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not callable(list_shards) or not refresh_gateway.can_enqueue():
            return None
        shard_keys = [str(item).strip() for item in list(list_shards(scope_key) or []) if str(item).strip()]
        if not shard_keys:
            mark_empty = getattr(self._projection_builder, empty_method_name, None)
            if callable(mark_empty):
                mark_empty(scope_key)
        enqueued_scope_keys = refresh_gateway.enqueue_many(scope_type, shard_keys, reason=shard_reason)
        self._complete_dirty_scope(event, scope_type=scope_type, scope_key=scope_key)
        return {"scope_key": scope_key, "enqueued_scope_keys": enqueued_scope_keys, "row_count": 0}

    def _complete_dirty_scope(self, event: RuntimeQueueEvent, *, scope_type: str, scope_key: str) -> None:
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=scope_type,
                scope_key=scope_key,
                source_version=event.source_version,
            )


def _invoice_scope_requires_expansion(scope_key: str) -> bool:
    return not MONTH_SCOPE_RE.match(str(scope_key or "").strip())
