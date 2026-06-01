from __future__ import annotations

from typing import Any, Callable


class TurnoverLedgerExtraRepositoryAdapter:
    def __init__(self, *, repository_factory: Callable[[Any], Any]) -> None:
        self._repository_factory = repository_factory

    def save_extra(self, extra: dict[str, object], *, transaction: Any) -> None:
        relation_id = str(extra.get("relation_id") or "").strip()
        if not relation_id:
            raise ValueError("relation_id is required.")
        repository = self._repository_factory(transaction)
        repository.save_turnover_ledger_extras({"extras": {relation_id: dict(extra)}})


class TurnoverLedgerDirtyOutboxWriter:
    def __init__(
        self,
        *,
        queue_repository: Any,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
    ) -> None:
        self._queue_repository = queue_repository
        self._tenant_id = str(tenant_id or "default")
        self._priority = str(priority or "normal")
        self._trace_id = str(trace_id).strip() if trace_id else None

    def enqueue_refresh(
        self,
        *,
        transaction: Any,
        scope_type: str,
        scope_keys: list[str],
        reason: str,
        payload: dict[str, object] | None = None,
    ) -> list[Any]:
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
        if not callable(enqueue):
            raise RuntimeError("queue_repository must expose enqueue_read_model_refresh_in_transaction.")
        events = []
        for scope_key in list(scope_keys or ["all"]):
            events.append(
                enqueue(
                    transaction=transaction,
                    scope_type=scope_type,
                    scope_key=str(scope_key or "all"),
                    reason=reason,
                    tenant_id=self._tenant_id,
                    priority=self._priority,
                    trace_id=self._trace_id,
                )
            )
        return events


class TurnoverLedgerExtraNormalizerAdapter:
    def __init__(self, *, extra_service: Any) -> None:
        self._extra_service = extra_service

    def __call__(self, *, relation_id: str, payload: dict[str, object], actor_id: str) -> dict[str, object]:
        normalize = getattr(self._extra_service, "normalize_update", None)
        if not callable(normalize):
            raise RuntimeError("extra_service must expose normalize_update.")
        return dict(normalize(relation_id, payload, actor=actor_id))
