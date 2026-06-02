from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fin_ops_platform.services.workbench_idempotency import workbench_request_fingerprint


@dataclass(frozen=True)
class TurnoverLedgerWriteCommand:
    action_name: str
    scope_keys: list[str] = field(default_factory=lambda: ["all"])
    refresh_requests: list[dict[str, object]] = field(default_factory=list)
    expected_versions: dict[str, object] = field(default_factory=dict)
    idempotency_key: str = ""
    request_fingerprint: str = ""
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
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        extra = self._extra_normalizer(
            relation_id=relation_id,
            payload=dict(payload),
            actor_id=actor_id,
        )
        normalized_expected_versions = dict(expected_versions or {})
        command_payload = {"relation_id": relation_id, "extra": dict(extra)}
        normalized_idempotency_key = str(idempotency_key or "").strip()
        request_fingerprint = ""
        action_name = "turnover_relation_extra_update" if normalized_idempotency_key else "relation_extra_update"
        if normalized_idempotency_key:
            request_fingerprint = workbench_request_fingerprint(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action_name=action_name,
                payload={
                    "relation_id": relation_id,
                    "extra": dict(extra),
                    "expected_versions": dict(normalized_expected_versions),
                },
            )
        command = TurnoverLedgerWriteCommand(
            action_name=action_name,
            scope_keys=list(scope_keys or ["all"]),
            refresh_requests=[
                {
                    "scope_type": "turnover_ledger",
                    "scope_keys": list(scope_keys or ["all"]),
                    "reason": "turnover_relation_extra_changed",
                }
            ],
            expected_versions=dict(normalized_expected_versions),
            idempotency_key=normalized_idempotency_key,
            request_fingerprint=request_fingerprint,
            actor_id=actor_id,
            tenant_id=tenant_id,
            payload=command_payload,
        )

        def handler(context: Any) -> dict[str, object]:
            context.extra_repository.save_extra(extra, transaction=context.transaction)
            result: dict[str, object] = {"extra": dict(extra)}
            if self._row_provider is not None:
                result["row"] = self._row_provider(relation_id=relation_id, extra=dict(extra))
            return result

        return self._uow.run(command, handler)

    def update_bank_row_tags_batch(
        self,
        *,
        updates: list[dict[str, object]],
        actor_id: str,
        tenant_id: str,
        affected_months: list[str],
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_updates = [dict(update) for update in list(updates or [])]
        normalized_months = [
            str(month).strip()
            for month in list(affected_months or [])
            if str(month).strip()
        ]
        refresh_requests = [
            {
                "scope_type": "bank_detail",
                "scope_keys": list(normalized_months),
                "reason": "bank_transaction_category_changed",
            },
            {
                "scope_type": "workbench",
                "scope_keys": list(normalized_months),
                "reason": "workbench_scope_invalidated",
            },
            {
                "scope_type": "turnover_ledger",
                "scope_keys": ["all"],
                "reason": "turnover_relation_changed",
            },
        ]
        normalized_idempotency_key = str(idempotency_key or "").strip()
        action_name = "turnover_bank_row_tags_batch" if normalized_idempotency_key else "bank_row_tags_batch"
        command_payload = {
            "updates": list(normalized_updates),
            "affected_months": list(normalized_months),
        }
        request_fingerprint = ""
        if normalized_idempotency_key:
            request_fingerprint = workbench_request_fingerprint(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action_name=action_name,
                payload=dict(command_payload),
            )
        command = TurnoverLedgerWriteCommand(
            action_name=action_name,
            scope_keys=["all"],
            refresh_requests=refresh_requests,
            actor_id=actor_id,
            tenant_id=tenant_id,
            idempotency_key=normalized_idempotency_key,
            request_fingerprint=request_fingerprint,
            payload=command_payload,
        )

        def handler(context: Any) -> dict[str, object]:
            result = context.bankdetail_port.apply_turnover_category_updates(
                list(normalized_updates),
                actor_id=actor_id,
                transaction=context.transaction,
            )
            payload = dict(result or {})
            payload.setdefault("affected_months", list(normalized_months))
            return payload

        return self._uow.run(command, handler)

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        tenant_id: str,
        note: str | None,
        affected_months: list[str],
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_bank_row_ids = [
            str(row_id).strip()
            for row_id in list(bank_row_ids or [])
            if str(row_id).strip()
        ]
        normalized_months = [
            str(month).strip()
            for month in list(affected_months or [])
            if str(month).strip()
        ]
        normalized_expected_versions = dict(expected_versions or {})
        normalized_idempotency_key = str(idempotency_key or "").strip()
        action_name = "turnover_relation_confirm" if normalized_idempotency_key else "confirm_relation"
        command_payload = {
            "bank_row_ids": list(normalized_bank_row_ids),
            "affected_months": list(normalized_months),
            "note": note,
        }
        request_fingerprint = ""
        if normalized_idempotency_key:
            request_fingerprint = workbench_request_fingerprint(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action_name=action_name,
                payload={
                    **dict(command_payload),
                    "expected_versions": dict(normalized_expected_versions),
                },
            )
        command = TurnoverLedgerWriteCommand(
            action_name=action_name,
            scope_keys=["all"],
            refresh_requests=[
                {
                    "scope_type": "turnover_ledger",
                    "scope_keys": ["all"],
                    "reason": "turnover_relation_changed",
                }
            ],
            actor_id=actor_id,
            tenant_id=tenant_id,
            expected_versions=dict(normalized_expected_versions),
            idempotency_key=normalized_idempotency_key,
            request_fingerprint=request_fingerprint,
            payload=command_payload,
        )

        def handler(context: Any) -> dict[str, object]:
            result = context.relation_repository.confirm_relation(
                bank_row_ids=list(normalized_bank_row_ids),
                actor_id=actor_id,
                note=note,
                transaction=context.transaction,
            )
            return dict(result or {})

        return self._uow.run(command, handler)

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor_id: str,
        tenant_id: str,
        note: str | None,
        affected_months: list[str],
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        normalized_relation_id = str(relation_id or "").strip()
        normalized_months = [
            str(month).strip()
            for month in list(affected_months or [])
            if str(month).strip()
        ]
        normalized_expected_versions = dict(expected_versions or {})
        normalized_idempotency_key = str(idempotency_key or "").strip()
        action_name = "turnover_relation_withdraw" if normalized_idempotency_key else "withdraw_relation"
        command_payload = {
            "relation_id": normalized_relation_id,
            "affected_months": list(normalized_months),
            "note": note,
        }
        request_fingerprint = ""
        if normalized_idempotency_key:
            request_fingerprint = workbench_request_fingerprint(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action_name=action_name,
                payload=dict(command_payload),
            )
        command = TurnoverLedgerWriteCommand(
            action_name=action_name,
            scope_keys=["all"],
            expected_versions=dict(normalized_expected_versions),
            refresh_requests=[
                {
                    "scope_type": "turnover_ledger",
                    "scope_keys": ["all"],
                    "reason": "turnover_relation_changed",
                }
            ],
            actor_id=actor_id,
            tenant_id=tenant_id,
            idempotency_key=normalized_idempotency_key,
            request_fingerprint=request_fingerprint,
            payload=command_payload,
        )

        def handler(context: Any) -> dict[str, object]:
            result = context.relation_repository.withdraw_relation(
                relation_id=normalized_relation_id,
                actor_id=actor_id,
                note=note,
                transaction=context.transaction,
            )
            return dict(result or {})

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
