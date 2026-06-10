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
    ) -> list[str]:
        return self.enqueue_many(
            scope_type,
            [scope_key],
            reason=reason,
            tenant_id=tenant_id,
            priority=priority,
            trace_id=trace_id,
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
    ) -> list[str]:
        normalized_scope_type = str(scope_type or "").strip()
        normalized_scope_keys = self._scope_policy_registry.normalize_and_validate(
            normalized_scope_type,
            scope_keys,
        )
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        for scope_key in normalized_scope_keys:
            if callable(enqueue):
                enqueue(**self._enqueue_kwargs(normalized_scope_type, scope_key, reason, tenant_id, priority, trace_id))
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
            events.append(enqueue(**self._enqueue_kwargs(normalized_scope_type, scope_key, reason, tenant_id, priority, trace_id)))
        return events

    @staticmethod
    def _enqueue_kwargs(
        scope_type: str,
        scope_key: str,
        reason: str,
        tenant_id: str,
        priority: str,
        trace_id: str | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"scope_type": scope_type, "scope_key": scope_key, "reason": reason}
        if tenant_id != "default":
            kwargs["tenant_id"] = tenant_id
        if priority != "normal":
            kwargs["priority"] = priority
        if trace_id is not None:
            kwargs["trace_id"] = trace_id
        return kwargs
