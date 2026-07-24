from __future__ import annotations

from typing import Any

from fin_ops_platform.services.read_model_scope_policy import (
    DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
    ReadModelScopePolicyRegistry,
)


class ReadModelRefreshGateway:
    def __init__(
        self,
        *,
        queue_repository: Any | None,
        scope_policy_registry: ReadModelScopePolicyRegistry = DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
    ) -> None:
        self._queue_repository = queue_repository
        self._scope_policy_registry = scope_policy_registry

    def can_enqueue(self) -> bool:
        return callable(getattr(self._queue_repository, "enqueue_read_model_refresh", None))

    def enqueue_one(
        self,
        scope_type: str,
        scope_key: str,
        *,
        reason: str,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        return self.enqueue_many(
            scope_type,
            [scope_key],
            reason=reason,
            tenant_id=tenant_id,
            priority=priority,
            trace_id=trace_id,
            metadata=metadata,
        )

    def enqueue_many(
        self,
        scope_type: str,
        scope_keys: list[str],
        *,
        reason: str,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        normalized_scope_type = str(scope_type or "").strip()
        normalized_scope_keys = self._scope_policy_registry.normalize_and_validate(
            normalized_scope_type,
            scope_keys,
        )
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        enqueue_if_inactive = getattr(
            self._queue_repository,
            "enqueue_read_model_refresh_if_inactive",
            None,
        )
        for scope_key in normalized_scope_keys:
            if callable(enqueue):
                enqueue_kwargs = self._enqueue_kwargs(
                    normalized_scope_type,
                    scope_key,
                    reason,
                    tenant_id,
                    priority,
                    trace_id,
                    metadata,
                )
                if callable(enqueue_if_inactive) and self._reason_uses_active_coalescing(
                    reason=reason,
                    metadata=metadata,
                ):
                    enqueue_if_inactive(**enqueue_kwargs)
                    continue
                if self._should_coalesce_active_refresh(
                    tenant_id=tenant_id,
                    scope_type=normalized_scope_type,
                    scope_key=scope_key,
                    reason=reason,
                    metadata=metadata,
                ):
                    continue
                enqueue(**enqueue_kwargs)
        return normalized_scope_keys

    def enqueue_many_events(
        self,
        scope_type: str,
        scope_keys: list[str],
        *,
        reason: str,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> list[Any]:
        normalized_scope_type = str(scope_type or "").strip()
        normalized_scope_keys = self._scope_policy_registry.normalize_and_validate(
            normalized_scope_type,
            scope_keys,
        )
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            return []
        enqueue_if_inactive = getattr(
            self._queue_repository,
            "enqueue_read_model_refresh_if_inactive",
            None,
        )
        events: list[Any] = []
        for scope_key in normalized_scope_keys:
            enqueue_kwargs = self._enqueue_kwargs(
                normalized_scope_type,
                scope_key,
                reason,
                tenant_id,
                priority,
                trace_id,
                metadata,
            )
            if callable(enqueue_if_inactive) and self._reason_uses_active_coalescing(
                reason=reason,
                metadata=metadata,
            ):
                event = enqueue_if_inactive(**enqueue_kwargs)
                if event is not None:
                    events.append(event)
                continue
            if self._should_coalesce_active_refresh(
                tenant_id=tenant_id,
                scope_type=normalized_scope_type,
                scope_key=scope_key,
                reason=reason,
                metadata=metadata,
            ):
                continue
            events.append(enqueue(**enqueue_kwargs))
        return events

    @staticmethod
    def _reason_uses_active_coalescing(
        *,
        reason: str,
        metadata: dict[str, object] | None,
    ) -> bool:
        return not (
            isinstance(metadata, dict)
            and metadata.get("force_refresh") is True
        ) and _reason_is_active_coalescible(reason)

    def _should_coalesce_active_refresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        reason: str,
        metadata: dict[str, object] | None,
    ) -> bool:
        if not self._reason_uses_active_coalescing(
            reason=reason,
            metadata=metadata,
        ):
            return False
        checker = getattr(self._queue_repository, "read_model_refresh_event_is_active", None)
        if not callable(checker):
            checker = getattr(self._queue_repository, "read_model_refresh_is_active", None)
        if not callable(checker):
            return False
        return bool(checker(tenant_id=tenant_id, scope_type=scope_type, scope_key=scope_key))

    @staticmethod
    def _enqueue_kwargs(
        scope_type: str,
        scope_key: str,
        reason: str,
        tenant_id: str,
        priority: str,
        trace_id: str | None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"scope_type": scope_type, "scope_key": scope_key, "reason": reason}
        if tenant_id != "default":
            kwargs["tenant_id"] = tenant_id
        if priority != "normal":
            kwargs["priority"] = priority
        if trace_id is not None:
            kwargs["trace_id"] = trace_id
        if isinstance(metadata, dict) and metadata:
            kwargs["metadata"] = dict(metadata)
        return kwargs


_ACTIVE_COALESCED_REFRESH_REASONS = {
    "dependency_not_fresh",
    "downstream_bank_tag_read",
    "pending_invoice_sql_projection",
    "bank_detail_all_shard",
    "bank_detail_relation_tags_read",
    "bank_details_relation_tag_projection",
    "cost_statistics_workbench_dependency_stale",
    "cost_statistics_bank_detail_dependency_stale",
    "cost_statistics_all_shard",
    "cost_statistics_shard_converged",
    "fan_out_command_scope",
    "input_invoice_usage_filter_options",
    "input_invoice_usage_month_shard",
    "input_invoice_usage_rows",
    "invoice_lifecycle_access_dependency",
    "invoice_lifecycle_month_shard",
    "invoice_usage_collection_sql_projection",
    "migration_missing",
    "oa_pending_payment_month_shard",
    "output_invoice_collection_month_shard",
    "output_invoice_collection_rows",
    "pending_invoice_month_shard",
    "relation_dependency_gate",
    "search_all_shard",
    "tax_offset_all_shard",
    "workbench_all_shard",
    "workbench_relation_write_precondition",
    "workbench_relation_month_shard",
}


def _reason_is_active_coalescible(reason: str) -> bool:
    normalized = str(reason or "").strip()
    if not normalized:
        return False
    return normalized.startswith("api_") or normalized in _ACTIVE_COALESCED_REFRESH_REASONS
