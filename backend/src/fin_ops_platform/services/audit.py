from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from itertools import count
from typing import Any

from fin_ops_platform.domain.models import AuditLog


class AuditTrailService:
    def __init__(self) -> None:
        self._sequence = count(1)
        self._entries: list[AuditLog] = []

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
        entry = AuditLog(
            id=f"audit_{next(self._sequence):04d}",
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_amount=before_amount,
            after_amount=after_amount,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        return entry

    def list_entries(self) -> list[AuditLog]:
        return list(self._entries)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self._entries]
