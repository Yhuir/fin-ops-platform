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
        for scope_key in normalized_scope_keys:
            if callable(enqueue):
                if self._should_coalesce_active_refresh(
                    tenant_id=tenant_id,
                    scope_type=normalized_scope_type,
                    scope_key=scope_key,
                    reason=reason,
                ):
                    continue
                enqueue(**self._enqueue_kwargs(normalized_scope_type, scope_key, reason, tenant_id, priority, trace_id, metadata))
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
        events: list[Any] = []
        for scope_key in normalized_scope_keys:
            if self._should_coalesce_active_refresh(
                tenant_id=tenant_id,
                scope_type=normalized_scope_type,
                scope_key=scope_key,
                reason=reason,
            ):
                continue
            events.append(enqueue(**self._enqueue_kwargs(normalized_scope_type, scope_key, reason, tenant_id, priority, trace_id, metadata)))
        return events

    def _should_coalesce_active_refresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        reason: str,
    ) -> bool:
        if not _reason_is_active_coalescible(reason):
            return False
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
    "bank_detail_relation_tags_read",
    "workbench_relation_write_precondition",
}


def _reason_is_active_coalescible(reason: str) -> bool:
    normalized = str(reason or "").strip()
    if not normalized:
        return False
    return normalized.startswith("api_") or normalized in _ACTIVE_COALESCED_REFRESH_REASONS
