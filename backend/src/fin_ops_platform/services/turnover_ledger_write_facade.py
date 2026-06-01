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
        extra_normalizer: Callable[..., dict[str, object]] | None = None,
        app_settings_service: Any | None = None,
        tag_selection_normalizer: Callable[..., dict[str, object]] | None = None,
    ) -> None:
        self._uow = uow
        self._row_provider = row_provider
        self._extra_normalizer = extra_normalizer or self._default_extra_normalizer
        self._tag_selection_normalizer = tag_selection_normalizer
        if self._tag_selection_normalizer is None and app_settings_service is not None:
            self._tag_selection_normalizer = getattr(
                app_settings_service,
                "normalize_turnover_ledger_tag_selection_update",
                None,
            )

    def update_relation_extra(
        self,
        *,
        relation_id: str,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        scope_keys: list[str] | None = None,
    ) -> dict[str, object]:
        extra = self._extra_normalizer(
            relation_id=relation_id,
            payload=dict(payload),
            actor_id=actor_id,
        )
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

    def update_tag_selection(
        self,
        *,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        scope_keys: list[str] | None = None,
    ) -> dict[str, object]:
        normalized_update = self._normalize_tag_selection(payload=dict(payload), actor_id=actor_id)
        public_payload = dict(normalized_update["public_payload"])
        command = TurnoverLedgerWriteCommand(
            action_name="turnover_ledger_tag_selection_changed",
            scope_keys=list(scope_keys or ["all"]),
            actor_id=actor_id,
            tenant_id=tenant_id,
            payload={
                "next_selection": dict(normalized_update["next_selection"]),
                "audit_event": dict(normalized_update["audit_event"]),
            },
        )

        def handler(context: Any) -> dict[str, object]:
            context.settings_port.save_tag_selection_settings(
                next_snapshot=dict(normalized_update["next_snapshot"]),
                audit_event=dict(normalized_update["audit_event"]),
                transaction=context.transaction,
            )
            return public_payload

        return self._uow.run(command, handler)

    @staticmethod
    def _default_extra_normalizer(
        *,
        relation_id: str,
        payload: dict[str, object],
        actor_id: str,
    ) -> dict[str, object]:
        extra = dict(payload)
        extra["relation_id"] = relation_id
        extra["updated_by"] = actor_id
        return extra

    def _normalize_tag_selection(self, *, payload: dict[str, object], actor_id: str) -> dict[str, object]:
        normalize = self._tag_selection_normalizer
        if not callable(normalize):
            raise RuntimeError("tag_selection_normalizer is required.")
        try:
            return dict(normalize(payload=payload, actor_id=actor_id))
        except TypeError:
            return dict(normalize(payload, actor_id=actor_id))
