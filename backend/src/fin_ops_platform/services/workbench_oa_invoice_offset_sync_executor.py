from __future__ import annotations

from typing import Any, Callable


class WorkbenchOaInvoiceOffsetSyncExecutor:
    """Synchronizes OA invoice offset auto-pair relations through explicit ports."""

    def __init__(
        self,
        *,
        desired_relations_builder: Callable[[dict[str, object]], dict[str, dict[str, object]]],
        raw_payload_row_ids: Callable[[dict[str, object]], set[str]],
        active_relations_for_mode: Callable[[str], list[dict[str, Any]]],
        command_service_provider: Callable[[], Any],
        persist_pair_relations: Callable[..., None],
        execute_lifecycle_event: Callable[..., object],
        relation_mode: str,
        actor_id: str = "system_auto_match",
        confirm_history_operation_type: str = "oa_invoice_offset_auto_pair",
        cancel_history_operation_type: str = "oa_invoice_offset_auto_pair_removed",
        cancel_reason: str = "OA 发票冲抵自动关系已不在当前工作台 payload 中。",
        lifecycle_event_name: str = "pair_relation_changed",
        lifecycle_source: str = "repair_active_relations_for_removed_rows",
    ) -> None:
        self._desired_relations_builder = desired_relations_builder
        self._raw_payload_row_ids = raw_payload_row_ids
        self._active_relations_for_mode = active_relations_for_mode
        self._command_service_provider = command_service_provider
        self._persist_pair_relations = persist_pair_relations
        self._execute_lifecycle_event = execute_lifecycle_event
        self._relation_mode = relation_mode
        self._actor_id = actor_id
        self._confirm_history_operation_type = confirm_history_operation_type
        self._cancel_history_operation_type = cancel_history_operation_type
        self._cancel_reason = cancel_reason
        self._lifecycle_event_name = lifecycle_event_name
        self._lifecycle_source = lifecycle_source

    def sync(self, payload: dict[str, object]) -> bool:
        desired_relations = self._desired_relations_builder(payload)
        scanned_row_ids = self._raw_payload_row_ids(payload)
        active_auto_relations = {
            str(relation.get("case_id")): relation
            for relation in self._active_relations_for_mode(self._relation_mode)
        }
        changed_case_ids: list[str] = []
        changed_scope_keys: set[str] = {"all"}
        command_service = self._command_service_provider()

        for case_id, desired_relation in desired_relations.items():
            existing_relation = active_auto_relations.get(case_id)
            if self._relation_already_matches(existing_relation, desired_relation):
                continue
            command_result = command_service.confirm_relation(
                case_id=case_id,
                row_ids=list(desired_relation["row_ids"]),
                row_types=list(desired_relation["row_types"]),
                relation_mode=self._relation_mode,
                actor_id=self._actor_id,
                month_scope=str(desired_relation["month_scope"]),
                history_operation_type=self._confirm_history_operation_type,
            )
            self._collect_changed_case_ids(changed_case_ids, command_result, fallback_case_id=case_id)
            self._collect_changed_scope(changed_scope_keys, desired_relation.get("month_scope"))

        for case_id in sorted(set(active_auto_relations).difference(desired_relations)):
            relation_row_ids = {str(row_id) for row_id in list(active_auto_relations[case_id].get("row_ids") or [])}
            if not scanned_row_ids or not relation_row_ids.intersection(scanned_row_ids):
                continue
            command_result = command_service.cancel_relation(
                case_id=case_id,
                actor_id=self._actor_id,
                reason=self._cancel_reason,
                history_operation_type=self._cancel_history_operation_type,
            )
            self._collect_changed_case_ids(changed_case_ids, command_result, fallback_case_id=case_id)
            self._collect_changed_scope(changed_scope_keys, active_auto_relations[case_id].get("month_scope"))

        if not changed_case_ids:
            return False
        self._persist_pair_relations(changed_case_ids=sorted(set(changed_case_ids)))
        self._execute_lifecycle_event(
            self._lifecycle_event_name,
            scope_keys=list(changed_scope_keys),
            metadata={"source": self._lifecycle_source},
        )
        return True

    def _relation_already_matches(
        self,
        existing_relation: dict[str, Any] | None,
        desired_relation: dict[str, object],
    ) -> bool:
        return (
            isinstance(existing_relation, dict)
            and list(existing_relation.get("row_ids") or []) == desired_relation["row_ids"]
            and str(existing_relation.get("relation_mode")) == self._relation_mode
            and str(existing_relation.get("month_scope")) == str(desired_relation["month_scope"])
            and str(existing_relation.get("status")) == "active"
        )

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

    @staticmethod
    def _collect_changed_scope(changed_scope_keys: set[str], month_scope: object) -> None:
        scope_key = str(month_scope or "").strip()
        if scope_key and scope_key != "all":
            changed_scope_keys.add(scope_key)
