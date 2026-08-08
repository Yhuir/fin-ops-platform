from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fin_ops_platform.domain.models import AuditLog
from fin_ops_platform.services.postgres_repositories.common import serialize_value, without_keys


_SENSITIVE_AUDIT_KEYS = {
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
}


class AuditTrailService:
    def __init__(self, repository: Any | None = None) -> None:
        self._repository = repository
        self._entries: list[AuditLog] = []

    @property
    def is_durable(self) -> bool:
        return self._repository is not None

    def record_action(
        self,
        *,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before_amount: Decimal | None = None,
        after_amount: Decimal | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        sanitized_metadata = without_keys(serialize_value(metadata or {}), _SENSITIVE_AUDIT_KEYS)
        created_at = sanitized_metadata.get("created_at") if isinstance(sanitized_metadata, dict) else None
        entry_id = str(uuid4())
        if self._repository is not None:
            persisted = self._repository.append_operation_event(
                {
                    "event_type": str(sanitized_metadata.get("event_type") or "operation.action"),
                    "object_type": entity_type,
                    "object_id": entity_id,
                    "actor_id": actor_id,
                    "actor_name": sanitized_metadata.get("actor_name"),
                    "scope": sanitized_metadata.get("scope"),
                    "trace_id": sanitized_metadata.get("trace_id"),
                    "occurred_at": created_at,
                    "action": action,
                    "page_key": sanitized_metadata.get("page_key") or sanitized_metadata.get("page"),
                    "operation_location": sanitized_metadata.get("operation_location") or "service",
                    "reason": sanitized_metadata.get("reason"),
                    "outcome": sanitized_metadata.get("outcome") or "success",
                    "request_id": sanitized_metadata.get("request_id"),
                    "payload": {
                        "before": {"amount": str(before_amount)} if before_amount is not None else None,
                        "after": {"amount": str(after_amount)} if after_amount is not None else None,
                        "metadata": sanitized_metadata,
                        "summary": sanitized_metadata.get("summary") or action,
                    },
                }
            )
            entry_id = str(persisted["id"])
        entry = AuditLog(
            id=entry_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_amount=before_amount,
            after_amount=after_amount,
            metadata=sanitized_metadata,
        )
        # In-memory entries only support isolated unit tests; PostgreSQL is the production fact source.
        if self._repository is None:
            self._entries.append(entry)
        return entry

    def list_entries(self) -> list[AuditLog]:
        return list(self._entries)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self._entries]
