from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class TurnoverLedgerWriteCommand:
    action_name: str
    scope_keys: list[str] = field(default_factory=lambda: ["all"])
    expected_versions: dict[str, object] = field(default_factory=dict)
    actor_id: str = ""
    tenant_id: str = "default"
    payload: dict[str, object] = field(default_factory=dict)


class TurnoverLedgerWriteFacade:
    def __init__(
        self,
        *,
        uow: Any,
        row_provider: Callable[..., dict[str, object]] | None = None,
    ) -> None:
        self._uow = uow
        self._row_provider = row_provider

    def update_relation_extra(
        self,
        *,
        relation_id: str,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        scope_keys: list[str] | None = None,
    ) -> dict[str, object]:
        extra = dict(payload)
        extra["relation_id"] = relation_id
        extra["updated_by"] = actor_id
        command = TurnoverLedgerWriteCommand(
            action_name="relation_extra_update",
            scope_keys=list(scope_keys or ["all"]),
            actor_id=actor_id,
            tenant_id=tenant_id,
            payload={"relation_id": relation_id, "extra": dict(extra)},
        )

        def handler(context: Any) -> dict[str, object]:
            context.extra_repository.save_extra(extra, transaction=context.transaction)
            result: dict[str, object] = {"extra": dict(extra)}
            if self._row_provider is not None:
                result["row"] = self._row_provider(relation_id=relation_id, extra=dict(extra))
            return result

        return self._uow.run(command, handler)
