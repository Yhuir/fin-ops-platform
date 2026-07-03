from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable


class WorkbenchOaAttachmentRepairContextExecutor:
    """Repairs active relations that are missing OA attachment context rows."""

    def __init__(
        self,
        *,
        raw_payload_rows_by_id: Callable[[dict[str, object]], dict[str, dict[str, object]]],
        attachment_row_ids_by_oa_id: Callable[[dict[str, dict[str, object]]], dict[str, list[str]]],
        active_relations: Callable[[], list[dict[str, Any]]],
        relation_requires_dedicated_withdraw_action: Callable[[dict[str, object]], bool],
        row_type_for_row_id: Callable[[str], str],
        serialize_value: Callable[[object], object],
        rows_by_type: Callable[[list[dict[str, object]]], dict[str, list[dict[str, object]]]],
        amount_check_for_rows_by_type: Callable[[dict[str, list[dict[str, object]]]], dict[str, object]],
        scope_keys_for_row_ids: Callable[..., set[str]],
        command_service_provider: Callable[[], Any],
        persist_pair_relations: Callable[..., None],
        execute_lifecycle_event: Callable[..., object],
        clock: Callable[[], datetime] | None = None,
        actor_id: str = "system_repair",
        fallback_relation_mode: str = "manual_confirmed",
        fallback_created_by: str = "system_repair",
        history_operation_type: str = "repair_missing_oa_attachment_context",
        history_note: str = "",
        lifecycle_event_name: str = "pair_relation_changed",
        lifecycle_source: str = "repair_active_relations_with_oa_attachment_context",
    ) -> None:
        self._raw_payload_rows_by_id = raw_payload_rows_by_id
        self._attachment_row_ids_by_oa_id = attachment_row_ids_by_oa_id
        self._active_relations = active_relations
        self._relation_requires_dedicated_withdraw_action = relation_requires_dedicated_withdraw_action
        self._row_type_for_row_id = row_type_for_row_id
        self._serialize_value = serialize_value
        self._rows_by_type = rows_by_type
        self._amount_check_for_rows_by_type = amount_check_for_rows_by_type
        self._scope_keys_for_row_ids = scope_keys_for_row_ids
        self._command_service_provider = command_service_provider
        self._persist_pair_relations = persist_pair_relations
        self._execute_lifecycle_event = execute_lifecycle_event
        self._clock = clock or (lambda: datetime.now(UTC))
        self._actor_id = actor_id
        self._fallback_relation_mode = fallback_relation_mode
        self._fallback_created_by = fallback_created_by
        self._history_operation_type = history_operation_type
        self._history_note = history_note
        self._lifecycle_event_name = lifecycle_event_name
        self._lifecycle_source = lifecycle_source

    def repair(self, payload: dict[str, object]) -> bool:
        rows_by_id = self._raw_payload_rows_by_id(payload)
        if not rows_by_id:
            return False
        attachment_row_ids_by_oa_id = self._attachment_row_ids_by_oa_id(rows_by_id)
        if not attachment_row_ids_by_oa_id:
            return False

        changed_case_ids: list[str] = []
        changed_scope_keys: set[str] = {"all"}
        timestamp = self._clock().isoformat()
        command_service = self._command_service_provider()
        for relation in self._active_relations():
            repair = self._repair_payload_for_relation(
                payload=payload,
                rows_by_id=rows_by_id,
                attachment_row_ids_by_oa_id=attachment_row_ids_by_oa_id,
                relation=relation,
                timestamp=timestamp,
            )
            if repair is None:
                continue
            command_result = command_service.confirm_relation(**repair.confirm_kwargs)
            repaired_relation = dict(command_result.get("relation") or {})
            case_id = str(repaired_relation.get("case_id") or "").strip()
            if case_id:
                self._collect_changed_case_ids(changed_case_ids, command_result, fallback_case_id=case_id)
            changed_scope_keys.update(
                self._scope_keys_for_row_ids(
                    month=str(payload.get("month") or "all"),
                    row_ids=repair.repaired_row_ids,
                    month_scope=str(repaired_relation.get("month_scope") or ""),
                )
            )

        if not changed_case_ids:
            return False
        self._persist_pair_relations(changed_case_ids=sorted(set(changed_case_ids)))
        self._execute_lifecycle_event(
            self._lifecycle_event_name,
            scope_keys=list(changed_scope_keys),
            metadata={"source": self._lifecycle_source},
        )
        return True

    def _repair_payload_for_relation(
        self,
        *,
        payload: dict[str, object],
        rows_by_id: dict[str, dict[str, object]],
        attachment_row_ids_by_oa_id: dict[str, list[str]],
        relation: dict[str, Any],
        timestamp: str,
    ) -> "_RepairPayload | None":
        if self._relation_requires_dedicated_withdraw_action(relation):
            return None
        row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()]
        if not row_ids:
            return None
        row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
        relation_row_ids = set(row_ids)
        relation_has_bank = any(
            self._relation_row_type(row_types, index, row_id) == "bank"
            for index, row_id in enumerate(row_ids)
        )
        if not relation_has_bank:
            return None
        oa_row_ids = [
            row_id
            for index, row_id in enumerate(row_ids)
            if self._relation_row_type(row_types, index, row_id) == "oa"
        ]
        missing_oa_row_ids = [
            oa_row_id
            for oa_row_id, attachment_row_ids in attachment_row_ids_by_oa_id.items()
            if oa_row_id not in relation_row_ids
            and oa_row_id in rows_by_id
            and any(attachment_row_id in relation_row_ids for attachment_row_id in attachment_row_ids)
        ]
        missing_attachment_row_ids: list[str] = []
        for oa_row_id in oa_row_ids:
            for attachment_row_id in attachment_row_ids_by_oa_id.get(oa_row_id, []):
                if attachment_row_id not in relation_row_ids and attachment_row_id in rows_by_id:
                    missing_attachment_row_ids.append(attachment_row_id)
        if not missing_oa_row_ids and not missing_attachment_row_ids:
            return None

        repaired_row_ids = [*row_ids, *missing_oa_row_ids, *missing_attachment_row_ids]
        repaired_row_types = [
            *[
                self._relation_row_type(row_types, index, row_id)
                for index, row_id in enumerate(row_ids)
            ],
            *(["oa"] * len(missing_oa_row_ids)),
            *(["invoice"] * len(missing_attachment_row_ids)),
        ]
        repaired_rows = [rows_by_id[row_id] for row_id in repaired_row_ids if row_id in rows_by_id]
        before_relation = self._serialize_value(relation)
        amount_check = self._amount_check_for_rows_by_type(self._rows_by_type(repaired_rows))
        return _RepairPayload(
            repaired_row_ids=repaired_row_ids,
            confirm_kwargs={
                "case_id": str(relation.get("case_id") or ""),
                "row_ids": repaired_row_ids,
                "row_types": repaired_row_types,
                "relation_mode": str(relation.get("relation_mode") or self._fallback_relation_mode),
                "actor_id": self._actor_id,
                "relation_created_by": str(relation.get("created_by") or self._fallback_created_by),
                "month_scope": str(relation.get("month_scope") or "all"),
                "note": str(relation.get("note") or ""),
                "amount_check": amount_check,
                "special_metadata": relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else None,
                "exception_case_id": str(relation.get("exception_case_id") or ""),
                "rule_version": str(relation.get("rule_version") or ""),
                "evidence": relation.get("evidence") if isinstance(relation.get("evidence"), dict) else None,
                "oa_exemption": relation.get("oa_exemption") if isinstance(relation.get("oa_exemption"), dict) else None,
                "display_tags": [
                    str(tag).strip()
                    for tag in list(relation.get("display_tags") or [])
                    if str(tag).strip()
                ],
                "occurred_at": timestamp,
                "before_relations": [before_relation],
                "replace_existing": True,
                "history_operation_type": self._history_operation_type,
                "history_note": self._history_note,
            },
        )

    def _relation_row_type(self, row_types: list[str], index: int, row_id: str) -> str:
        if index < len(row_types) and row_types[index]:
            return row_types[index]
        return self._row_type_for_row_id(row_id)

    @staticmethod
    def _collect_changed_case_ids(
        changed_case_ids: list[str],
        command_result: dict[str, object],
        *,
        fallback_case_id: str,
    ) -> None:
        changed_case_ids.extend(
            str(changed_case_id)
            for changed_case_id in list(command_result.get("changed_case_ids") or [fallback_case_id])
            if str(changed_case_id).strip()
        )


class _RepairPayload:
    def __init__(self, *, repaired_row_ids: list[str], confirm_kwargs: dict[str, object]) -> None:
        self.repaired_row_ids = repaired_row_ids
        self.confirm_kwargs = confirm_kwargs
