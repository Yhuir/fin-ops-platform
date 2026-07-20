from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fin_ops_platform.services.oa_attachment_invoice_linking import oa_attachment_row_id_matches_oa
from fin_ops_platform.services.workbench_relation_modes import (
    DISPLAY_ONLY_WORKBENCH_RELATION_MODES,
    is_workbench_relation_snapshot_restorable,
    mark_relation_restorable_on_withdraw,
    relation_mode_can_be_restored_on_withdraw,
    workbench_relations_have_same_row_set,
)
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


ACTIVE_PAIR_RELATION_STATUS = "active"
CANCELLED_PAIR_RELATION_STATUS = "cancelled"
DISPLAY_ONLY_PAIR_RELATION_MODES = set(DISPLAY_ONLY_WORKBENCH_RELATION_MODES)
WITHDRAW_RESTORABLE_CONFIRM_OPERATION_TYPES = frozenset(
    {
        "confirm_link",
        "turnover_manual_closure_confirm",
    }
)


class WorkbenchPairRelationService:
    def __init__(
        self,
        *,
        pair_relations: dict[str, dict[str, Any]] | None = None,
        pair_relation_history: list[dict[str, Any]] | None = None,
    ) -> None:
        self._pair_relations = self._normalize_pair_relations(pair_relations or {})
        self._pair_relation_history = self._normalize_history(pair_relation_history or [])

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchPairRelationService":
        if not snapshot:
            return cls()
        pair_relations = snapshot.get("pair_relations")
        pair_relation_history = snapshot.get("pair_relation_history")
        return cls(
            pair_relations=pair_relations if isinstance(pair_relations, dict) else {},
            pair_relation_history=pair_relation_history if isinstance(pair_relation_history, list) else [],
        )

    def snapshot(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"pair_relations": deepcopy(self._pair_relations)}
        if self._pair_relation_history:
            payload["pair_relation_history"] = deepcopy(self._pair_relation_history)
        return payload

    def apply_snapshot_delta(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: list[str] | set[str] | None = None,
        replace_history: bool = True,
    ) -> None:
        changed_ids = {
            str(case_id).strip()
            for case_id in list(changed_case_ids or [])
            if str(case_id).strip()
        }
        incoming = self.from_snapshot(snapshot)

        if changed_ids:
            for case_id in changed_ids:
                relation = incoming._pair_relations.get(case_id)
                if relation is None:
                    self._pair_relations.pop(case_id, None)
                else:
                    self._pair_relations[case_id] = deepcopy(relation)
            if replace_history:
                self._pair_relation_history = [
                    history
                    for history in self._pair_relation_history
                    if not self._history_touches_cases(history, changed_ids)
                ]
        else:
            self._pair_relations.update(deepcopy(incoming._pair_relations))

        if not replace_history and incoming._pair_relation_history:
            incoming_operation_ids = {
                str(history.get("operation_id") or "").strip()
                for history in incoming._pair_relation_history
                if str(history.get("operation_id") or "").strip()
            }
            if incoming_operation_ids:
                self._pair_relation_history = [
                    history
                    for history in self._pair_relation_history
                    if str(history.get("operation_id") or "").strip() not in incoming_operation_ids
                ]
        self._pair_relation_history.extend(deepcopy(incoming._pair_relation_history))

    def snapshot_case_ids(self, case_ids: list[str], *, include_history: bool = True) -> dict[str, Any]:
        normalized_case_ids = {
            str(case_id).strip()
            for case_id in list(case_ids or [])
            if str(case_id).strip()
        }
        payload: dict[str, Any] = {
            "pair_relations": {
                case_id: deepcopy(relation)
                for case_id, relation in self._pair_relations.items()
                if case_id in normalized_case_ids
            }
        }
        if include_history and self._pair_relation_history and normalized_case_ids:
            payload["pair_relation_history"] = [
                deepcopy(history)
                for history in self._pair_relation_history
                if self._history_touches_cases(history, normalized_case_ids)
            ]
        return payload

    def snapshot_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_row_ids = {
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        }
        normalized_case_ids = {
            str(case_id).strip()
            for case_id in list(case_ids or [])
            if str(case_id).strip()
        }
        if not normalized_row_ids and not normalized_case_ids:
            return {}

        selected_relations: dict[str, dict[str, Any]] = {}
        for case_id, relation in self._pair_relations.items():
            relation_row_ids = {
                str(row_id).strip()
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            }
            if case_id in normalized_case_ids or normalized_row_ids.intersection(relation_row_ids):
                selected_relations[case_id] = deepcopy(relation)

        selected_case_ids = {*normalized_case_ids, *selected_relations}
        payload: dict[str, Any] = {"pair_relations": selected_relations}
        if self._pair_relation_history and selected_case_ids:
            payload["pair_relation_history"] = [
                deepcopy(history)
                for history in self._pair_relation_history
                if self._history_touches_cases(history, selected_case_ids)
            ]
        return payload

    def list_active_relations(self) -> list[dict[str, Any]]:
        return [
            deepcopy(relation)
            for relation in self._pair_relations.values()
            if relation.get("status") == ACTIVE_PAIR_RELATION_STATUS
        ]

    def create_active_relation(
        self,
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        relation_mode: str,
        created_by: str,
        month_scope: str = "all",
        created_at: str | None = None,
        note: str | None = None,
        amount_check: dict[str, Any] | None = None,
        special_metadata: dict[str, Any] | None = None,
        exception_case_id: str | None = None,
        rule_version: str | None = None,
        evidence: dict[str, Any] | None = None,
        oa_exemption: dict[str, Any] | None = None,
        display_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        resolved_case_id = str(case_id).strip()
        if not resolved_case_id:
            raise ValueError("case_id is required for pair relation creation.")

        timestamp = created_at or self._timestamp()
        existing_relation = self._pair_relations.get(resolved_case_id)
        normalized_row_ids, normalized_row_types = self._normalize_relation_entries(row_ids, row_types)
        requested_row_ids = set(normalized_row_ids)
        if isinstance(existing_relation, dict) and existing_relation.get("status") == ACTIVE_PAIR_RELATION_STATUS:
            existing_row_ids = {
                str(row_id).strip()
                for row_id in list(existing_relation.get("row_ids") or [])
                if str(row_id).strip()
            }
            if existing_row_ids and requested_row_ids and existing_row_ids.isdisjoint(requested_row_ids):
                raise ValueError(f"pair relation case_id already active for different rows: {resolved_case_id}")
        if requested_row_ids:
            for active_case_id, active_relation in self._pair_relations.items():
                if active_case_id == resolved_case_id:
                    continue
                if active_relation.get("status") != ACTIVE_PAIR_RELATION_STATUS:
                    continue
                active_row_ids = {
                    str(row_id).strip()
                    for row_id in list(active_relation.get("row_ids") or [])
                    if str(row_id).strip()
                }
                overlapping_row_ids = requested_row_ids.intersection(active_row_ids)
                if overlapping_row_ids:
                    raise ValueError(
                        "pair relation row already active in another case: "
                        f"{','.join(sorted(overlapping_row_ids))}"
                    )
        relation = self._normalize_relation(
            {
                **(deepcopy(existing_relation) if isinstance(existing_relation, dict) else {}),
                "case_id": resolved_case_id,
                "row_ids": normalized_row_ids,
                "row_types": normalized_row_types,
                "status": ACTIVE_PAIR_RELATION_STATUS,
                "relation_mode": relation_mode,
                "month_scope": month_scope,
                "created_by": created_by,
                "note": str(note).strip() if note is not None else "",
                "amount_check": deepcopy(amount_check) if isinstance(amount_check, dict) else {},
                "special_metadata": (
                    deepcopy(special_metadata)
                    if isinstance(special_metadata, dict)
                    else deepcopy(existing_relation.get("special_metadata"))
                    if isinstance(existing_relation, dict) and isinstance(existing_relation.get("special_metadata"), dict)
                    else {}
                ),
                "exception_case_id": str(exception_case_id or "").strip(),
                "rule_version": str(rule_version or "").strip(),
                "evidence": deepcopy(evidence) if isinstance(evidence, dict) else {},
                "oa_exemption": deepcopy(oa_exemption) if isinstance(oa_exemption, dict) else None,
                "display_tags": [
                    str(tag).strip()
                    for tag in list(display_tags or [])
                    if str(tag).strip()
                ],
                "created_at": (
                    str(existing_relation.get("created_at"))
                    if isinstance(existing_relation, dict) and existing_relation.get("created_at")
                    else timestamp
                ),
                "updated_at": timestamp,
            },
            fallback_case_id=resolved_case_id,
        )
        self._pair_relations[resolved_case_id] = relation
        return deepcopy(relation)

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        resolved_row_ids = {str(row_id).strip() for row_id in row_ids if str(row_id).strip()}
        relations_by_case_id: dict[str, dict[str, Any]] = {}
        for relation in self._pair_relations.values():
            if relation.get("status") != ACTIVE_PAIR_RELATION_STATUS:
                continue
            relation_row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            if resolved_row_ids.intersection(relation_row_ids):
                relations_by_case_id[str(relation.get("case_id", ""))] = deepcopy(relation)
        return list(relations_by_case_id.values())

    def replace_with_confirmed_relation(
        self,
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        relation_mode: str,
        created_by: str,
        month_scope: str = "all",
        note: str | None = None,
        amount_check: dict[str, Any] | None = None,
        special_metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
        before_relations: list[dict[str, Any]] | None = None,
        operation_type: str = "confirm_link",
        history_created_by: str | None = None,
        history_note: str | None = None,
        exception_case_id: str | None = None,
        rule_version: str | None = None,
        evidence: dict[str, Any] | None = None,
        oa_exemption: dict[str, Any] | None = None,
        display_tags: list[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        normalized_row_ids, normalized_row_types = self._normalize_relation_entries(row_ids, row_types)
        active_before_relations = self.active_relations_for_row_ids(normalized_row_ids)
        replacement_relation = {
            "row_ids": normalized_row_ids,
            "row_types": normalized_row_types,
        }
        history_before_relations = (
            self._restorable_relation_snapshots(
                self._mark_owned_before_relations_restorable(before_relations, active_before_relations),
                active_relation=replacement_relation,
            )
            if before_relations is not None
            else self._restorable_relation_snapshots(
                self._mark_owned_before_relations_restorable(active_before_relations, active_before_relations),
                active_relation=replacement_relation,
            )
        )
        timestamp = created_at or self._timestamp()
        for relation in active_before_relations:
            self.cancel_relation(str(relation.get("case_id", "")), cancelled_at=timestamp)
        after_relation = self.create_active_relation(
            case_id=case_id,
            row_ids=normalized_row_ids,
            row_types=normalized_row_types,
            relation_mode=relation_mode,
            created_by=created_by,
            month_scope=month_scope,
            created_at=timestamp,
            note=note,
            amount_check=amount_check,
            special_metadata=special_metadata,
            exception_case_id=exception_case_id,
            rule_version=rule_version,
            evidence=evidence,
            oa_exemption=oa_exemption,
            display_tags=display_tags,
        )
        history = self.record_history(
            operation_type=operation_type,
            before_relations=history_before_relations,
            after_relations=[after_relation],
            affected_row_ids=normalized_row_ids,
            created_by=history_created_by or created_by,
            note=history_note if history_note is not None else note,
            amount_check=amount_check,
            created_at=timestamp,
        )
        return after_relation, history

    def update_special_metadata_for_row_ids(
        self,
        row_ids: list[str],
        *,
        special_metadata: dict[str, Any],
        updated_by: str,
        note: str | None = None,
        updated_at: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        active_relation = self._active_relation_for_any_row_id(row_ids)
        if not isinstance(active_relation, dict):
            raise KeyError("workbench_pair_relation_not_found")
        timestamp = updated_at or self._timestamp()
        before_relation = deepcopy(active_relation)
        merged_metadata = {
            **deepcopy(active_relation.get("special_metadata") if isinstance(active_relation.get("special_metadata"), dict) else {}),
            **deepcopy(special_metadata),
            "updated_by": str(updated_by or ""),
        }
        if not merged_metadata.get("created_by"):
            merged_metadata["created_by"] = str(updated_by or "")
        normalized_relation = self._normalize_relation(
            {
                **deepcopy(active_relation),
                "special_metadata": merged_metadata,
                "updated_at": timestamp,
            },
            fallback_case_id=str(active_relation.get("case_id") or ""),
        )
        self._pair_relations[str(normalized_relation["case_id"])] = normalized_relation
        history = self.record_history(
            operation_type="update_special_relation",
            before_relations=[before_relation],
            after_relations=[normalized_relation],
            affected_row_ids=list(normalized_relation.get("row_ids") or []),
            created_by=updated_by,
            note=note,
            amount_check=dict(normalized_relation.get("amount_check") or {}),
            created_at=timestamp,
        )
        return deepcopy(normalized_relation), history

    def update_relation_metadata_for_case_id(
        self,
        case_id: str,
        *,
        relation_mode: str | None = None,
        amount_check: dict[str, Any] | None = None,
        special_metadata: dict[str, Any] | None = None,
        display_tags: list[str] | None = None,
        updated_by: str,
        note: str | None = None,
        updated_at: str | None = None,
        operation_type: str = "update_pair_relation_metadata",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        active_relation = self.get_active_relation_by_case_id(case_id)
        if not isinstance(active_relation, dict):
            raise KeyError("workbench_pair_relation_not_found")
        timestamp = updated_at or self._timestamp()
        before_relation = deepcopy(active_relation)
        merged_metadata = {
            **deepcopy(active_relation.get("special_metadata") if isinstance(active_relation.get("special_metadata"), dict) else {}),
            **deepcopy(special_metadata if isinstance(special_metadata, dict) else {}),
        }
        merged_display_tags = [
            str(tag).strip()
            for tag in [
                *list(active_relation.get("display_tags") or []),
                *list(display_tags or []),
            ]
            if str(tag).strip()
        ]
        merged_display_tags = list(dict.fromkeys(merged_display_tags))
        normalized_relation = self._normalize_relation(
            {
                **deepcopy(active_relation),
                "relation_mode": str(
                    relation_mode or active_relation.get("relation_mode") or "manual_confirmed"
                ).strip(),
                "amount_check": deepcopy(amount_check) if isinstance(amount_check, dict) else deepcopy(active_relation.get("amount_check") or {}),
                "special_metadata": merged_metadata,
                "display_tags": merged_display_tags,
                "updated_at": timestamp,
            },
            fallback_case_id=str(active_relation.get("case_id") or ""),
        )
        self._pair_relations[str(normalized_relation["case_id"])] = normalized_relation
        history = self.record_history(
            operation_type=operation_type,
            before_relations=[before_relation],
            after_relations=[normalized_relation],
            affected_row_ids=list(normalized_relation.get("row_ids") or []),
            created_by=updated_by,
            note=note,
            amount_check=dict(normalized_relation.get("amount_check") or {}),
            created_at=timestamp,
        )
        return deepcopy(normalized_relation), history

    def clear_special_metadata_for_row_ids(
        self,
        row_ids: list[str],
        *,
        updated_by: str,
        note: str | None = None,
        updated_at: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        active_relation = self._active_relation_for_any_row_id(row_ids)
        if not isinstance(active_relation, dict):
            raise KeyError("workbench_pair_relation_not_found")
        timestamp = updated_at or self._timestamp()
        before_relation = deepcopy(active_relation)
        normalized_relation = self._normalize_relation(
            {
                **deepcopy(active_relation),
                "special_metadata": {},
                "updated_at": timestamp,
            },
            fallback_case_id=str(active_relation.get("case_id") or ""),
        )
        self._pair_relations[str(normalized_relation["case_id"])] = normalized_relation
        history = self.record_history(
            operation_type="clear_special_relation",
            before_relations=[before_relation],
            after_relations=[normalized_relation],
            affected_row_ids=list(normalized_relation.get("row_ids") or []),
            created_by=updated_by,
            note=note,
            amount_check=dict(normalized_relation.get("amount_check") or {}),
            created_at=timestamp,
        )
        return deepcopy(normalized_relation), history

    def preview_withdraw_for_row_ids(
        self,
        row_ids: list[str],
        *,
        row_id_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        active_relation = self._active_relation_for_any_row_id(row_ids)
        if not isinstance(active_relation, dict):
            raise KeyError("workbench_pair_relation_not_found")
        confirm_history = self._latest_confirm_history_for_relation(active_relation)
        after_relations = (
            self._restorable_relation_snapshots(
                confirm_history.get("before_relations") or [],
                active_relation=active_relation,
                row_id_aliases=row_id_aliases,
            )
            if isinstance(confirm_history, dict)
            else []
        )
        after_relations = self._preserve_oa_attachment_bindings(
            after_relations,
            active_relation=active_relation,
            row_id_aliases=row_id_aliases,
        )
        return {
            "active_relation": deepcopy(active_relation),
            "confirm_history": deepcopy(confirm_history) if isinstance(confirm_history, dict) else {},
            "before_relations": [deepcopy(active_relation)],
            "after_relations": after_relations,
        }

    def withdraw_latest_for_row_ids(
        self,
        row_ids: list[str],
        *,
        created_by: str,
        note: str | None = None,
        created_at: str | None = None,
        fallback_after_relations: list[dict[str, Any]] | None = None,
        row_id_aliases: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        preview = self.preview_withdraw_for_row_ids(row_ids, row_id_aliases=row_id_aliases)
        active_relation = preview["active_relation"]
        if self.is_immutable_oa_attachment_binding_relation(
            active_relation,
            row_id_aliases=row_id_aliases,
        ):
            raise ValueError("immutable_oa_attachment_binding")
        restored_relations = list(preview["after_relations"])
        if not restored_relations and fallback_after_relations:
            restored_relations = self._restorable_relation_snapshots(
                fallback_after_relations,
                active_relation=active_relation,
                row_id_aliases=row_id_aliases,
            )
        restored_relations = self._preserve_oa_attachment_bindings(
            restored_relations,
            active_relation=active_relation,
            row_id_aliases=row_id_aliases,
        )
        timestamp = created_at or self._timestamp()
        self.cancel_relation(str(active_relation.get("case_id", "")), cancelled_at=timestamp)
        normalized_restored_relations: list[dict[str, Any]] = []
        for relation in restored_relations:
            if not isinstance(relation, dict):
                continue
            restored = self._normalize_relation(
                {
                    **deepcopy(relation),
                    "status": ACTIVE_PAIR_RELATION_STATUS,
                    "updated_at": timestamp,
                },
                fallback_case_id=str(relation.get("case_id", "")),
            )
            self._pair_relations[str(restored["case_id"])] = restored
            normalized_restored_relations.append(restored)
        affected_row_ids = [
            str(row_id)
            for relation in [active_relation, *normalized_restored_relations]
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        history = self.record_history(
            operation_type="withdraw_link",
            before_relations=[active_relation],
            after_relations=normalized_restored_relations,
            affected_row_ids=affected_row_ids,
            created_by=created_by,
            note=note,
            amount_check=dict(active_relation.get("amount_check") or {}),
            created_at=timestamp,
        )
        return deepcopy(normalized_restored_relations), history

    def cancel_active_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        created_by: str,
        note: str | None = None,
        created_at: str | None = None,
        operation_type: str = "cancel_active_relation",
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        resolved_row_ids = {
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        }
        if not resolved_row_ids:
            return [], None

        before_relations = self.active_relations_for_row_ids(sorted(resolved_row_ids))
        if not before_relations:
            return [], None

        timestamp = created_at or self._timestamp()
        cancelled_relations: list[dict[str, Any]] = []
        for relation in before_relations:
            cancelled = self.cancel_relation(str(relation.get("case_id", "")), cancelled_at=timestamp)
            if isinstance(cancelled, dict):
                cancelled_relations.append(cancelled)

        affected_row_ids = [
            str(row_id).strip()
            for relation in before_relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        history = self.record_history(
            operation_type=operation_type,
            before_relations=before_relations,
            after_relations=[],
            affected_row_ids=affected_row_ids,
            created_by=created_by,
            note=note,
            amount_check=dict(before_relations[0].get("amount_check") or {}),
            created_at=timestamp,
        )
        return deepcopy(cancelled_relations), history

    def record_history(
        self,
        *,
        operation_type: str,
        before_relations: list[dict[str, Any]],
        after_relations: list[dict[str, Any]],
        affected_row_ids: list[str],
        created_by: str,
        note: str | None = None,
        amount_check: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        history = self._normalize_history_entry(
            {
                "operation_id": uuid4().hex,
                "operation_type": operation_type,
                "before_relations": deepcopy(before_relations),
                "after_relations": deepcopy(after_relations),
                "affected_row_ids": list(affected_row_ids),
                "note": str(note).strip() if note is not None else "",
                "amount_check": deepcopy(amount_check) if isinstance(amount_check, dict) else {},
                "created_by": created_by,
                "created_at": created_at or self._timestamp(),
            }
        )
        self._pair_relation_history.append(history)
        return deepcopy(history)

    def list_history(self) -> list[dict[str, Any]]:
        return deepcopy(self._pair_relation_history)

    def get_active_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        resolved_case_id = str(case_id).strip()
        if not resolved_case_id:
            return None
        relation = self._pair_relations.get(resolved_case_id)
        if not isinstance(relation, dict):
            return None
        if relation.get("status") != ACTIVE_PAIR_RELATION_STATUS:
            return None
        return deepcopy(relation)

    def get_active_relation_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        resolved_row_id = str(row_id).strip()
        if not resolved_row_id:
            return None
        for relation in self._pair_relations.values():
            if relation.get("status") != ACTIVE_PAIR_RELATION_STATUS:
                continue
            row_ids = relation.get("row_ids")
            if isinstance(row_ids, list) and resolved_row_id in row_ids:
                return deepcopy(relation)
        return None

    def cancel_relation(self, case_id: str, *, cancelled_at: str | None = None) -> dict[str, Any] | None:
        resolved_case_id = str(case_id).strip()
        if not resolved_case_id:
            return None
        relation = self._pair_relations.get(resolved_case_id)
        if not isinstance(relation, dict):
            return None
        normalized_relation = self._normalize_relation(
            {
                **deepcopy(relation),
                "status": CANCELLED_PAIR_RELATION_STATUS,
                "updated_at": cancelled_at or self._timestamp(),
            },
            fallback_case_id=resolved_case_id,
        )
        self._pair_relations[resolved_case_id] = normalized_relation
        return deepcopy(normalized_relation)

    def cancel_relation_for_row_id(self, row_id: str, *, cancelled_at: str | None = None) -> dict[str, Any] | None:
        relation = self.get_active_relation_by_row_id(row_id)
        if not isinstance(relation, dict):
            return None
        return self.cancel_relation(str(relation.get("case_id", "")), cancelled_at=cancelled_at)

    @classmethod
    def is_immutable_oa_attachment_binding_relation(
        cls,
        relation: dict[str, Any],
        *,
        row_id_aliases: dict[str, str] | None = None,
    ) -> bool:
        metadata = relation.get("special_metadata")
        if isinstance(metadata, dict) and metadata.get("immutable_oa_attachment_binding") is True:
            row_types = {
                cls._relation_row_type(relation, str(row_id))
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            }
            if row_types and row_types <= {"oa", "invoice"}:
                return True
        binding_row_ids: set[str] = set()
        for binding_relation in cls._oa_attachment_binding_relations(
            relation,
            row_id_aliases=row_id_aliases,
        ):
            binding_row_ids.update(
                cls._relation_row_id_set(binding_relation, row_id_aliases=row_id_aliases)
            )
        relation_row_ids = cls._relation_row_id_set(relation, row_id_aliases=row_id_aliases)
        return bool(binding_row_ids) and relation_row_ids == binding_row_ids

    @classmethod
    def _normalize_pair_relations(cls, pair_relations: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for case_id, relation in pair_relations.items():
            if not isinstance(relation, dict):
                continue
            normalized_relation = cls._normalize_relation(relation, fallback_case_id=str(case_id))
            normalized[str(normalized_relation["case_id"])] = normalized_relation
        return normalized

    @classmethod
    def _normalize_relation(cls, relation: dict[str, Any], *, fallback_case_id: str) -> dict[str, Any]:
        resolved_case_id = str(relation.get("case_id") or fallback_case_id).strip()
        if not resolved_case_id:
            raise ValueError("pair relation requires a non-empty case_id")

        normalized = deepcopy(relation)
        normalized["case_id"] = resolved_case_id
        normalized_row_ids, normalized_row_types = cls._normalize_relation_entries(
            list(relation.get("row_ids") or []),
            list(relation.get("row_types") or []),
        )
        normalized["row_ids"] = normalized_row_ids
        normalized["row_types"] = normalized_row_types
        normalized["status"] = str(relation.get("status") or ACTIVE_PAIR_RELATION_STATUS)
        normalized["relation_mode"] = str(relation.get("relation_mode") or "manual_confirmed")
        normalized["month_scope"] = str(relation.get("month_scope") or "all")
        created_by = relation.get("created_by")
        normalized["created_by"] = "" if created_by is None else str(created_by)
        normalized["note"] = str(relation.get("note") or "")
        amount_check = relation.get("amount_check")
        normalized["amount_check"] = deepcopy(amount_check) if isinstance(amount_check, dict) else {}
        special_metadata = relation.get("special_metadata")
        normalized["special_metadata"] = deepcopy(special_metadata) if isinstance(special_metadata, dict) else {}
        normalized["exception_case_id"] = str(relation.get("exception_case_id") or "")
        normalized["rule_version"] = str(relation.get("rule_version") or "")
        evidence = relation.get("evidence")
        normalized["evidence"] = deepcopy(evidence) if isinstance(evidence, dict) else {}
        oa_exemption = relation.get("oa_exemption")
        normalized["oa_exemption"] = deepcopy(oa_exemption) if isinstance(oa_exemption, dict) else None
        normalized["display_tags"] = [
            str(tag).strip()
            for tag in list(relation.get("display_tags") or [])
            if str(tag).strip()
        ]
        normalized["created_at"] = str(relation.get("created_at") or cls._timestamp())
        normalized["updated_at"] = str(relation.get("updated_at") or normalized["created_at"])
        return normalized

    @classmethod
    def _normalize_relation_entries(cls, row_ids: list[Any], row_types: list[Any]) -> tuple[list[str], list[str]]:
        normalized_row_ids: list[str] = []
        normalized_row_types: list[str] = []
        seen_indexes: dict[str, int] = {}
        raw_row_types = list(row_types or [])
        for index, raw_row_id in enumerate(list(row_ids or [])):
            row_id = str(raw_row_id).strip()
            if not row_id:
                continue
            row_type = (
                str(raw_row_types[index]).strip()
                if index < len(raw_row_types)
                else ""
            ) or cls._row_type_for_row_id(row_id)
            seen_index = seen_indexes.get(row_id)
            if seen_index is not None:
                existing_type = normalized_row_types[seen_index]
                if row_type != existing_type and "unknown" not in {row_type, existing_type}:
                    raise ValueError(f"pair relation row_id has conflicting row type: {row_id}")
                if existing_type == "unknown" and row_type != "unknown":
                    normalized_row_types[seen_index] = row_type
                continue
            seen_indexes[row_id] = len(normalized_row_ids)
            normalized_row_ids.append(row_id)
            normalized_row_types.append(row_type)
        return normalized_row_ids, normalized_row_types

    @staticmethod
    def _row_type_for_row_id(row_id: str) -> str:
        return row_type_for_workbench_row_id(row_id)

    @classmethod
    def _preserve_oa_attachment_bindings(
        cls,
        relations: list[dict[str, Any]] | None,
        *,
        active_relation: dict[str, Any],
        row_id_aliases: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        preserved = [deepcopy(relation) for relation in list(relations or []) if isinstance(relation, dict)]
        for binding_relation in cls._oa_attachment_binding_relations(
            active_relation,
            row_id_aliases=row_id_aliases,
        ):
            binding_row_ids = cls._relation_row_id_set(
                binding_relation,
                row_id_aliases=row_id_aliases,
            )
            target_indexes = [
                index
                for index, relation in enumerate(preserved)
                if cls._relation_row_id_set(relation, row_id_aliases=row_id_aliases).intersection(binding_row_ids)
            ]
            if not target_indexes:
                preserved.append(binding_relation)
                continue

            merged = preserved[target_indexes[0]]
            for index in target_indexes[1:]:
                merged = cls._append_relation_rows(merged, preserved[index])
            merged = cls._append_relation_rows(merged, binding_relation)
            parent_oa_row_id = str(binding_relation.get("special_metadata", {}).get("parent_oa_row_id") or "")
            special_metadata = merged.get("special_metadata")
            merged["special_metadata"] = {
                **(deepcopy(special_metadata) if isinstance(special_metadata, dict) else {}),
                "contains_immutable_oa_attachment_binding": True,
                "parent_oa_row_id": parent_oa_row_id,
            }
            if cls._relation_row_id_set(merged, row_id_aliases=row_id_aliases) == binding_row_ids:
                merged["special_metadata"] = {
                    **deepcopy(merged["special_metadata"]),
                    "source": "oa_attachment_invoice",
                    "immutable_oa_attachment_binding": True,
                }

            target_index_set = set(target_indexes)
            preserved = [
                merged if index == target_indexes[0] else relation
                for index, relation in enumerate(preserved)
                if index == target_indexes[0] or index not in target_index_set
            ]
        return preserved

    @classmethod
    def _oa_attachment_binding_relations(
        cls,
        relation: dict[str, Any],
        *,
        row_id_aliases: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(relation, dict):
            return []
        row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()]
        oa_row_ids = [
            row_id
            for row_id in row_ids
            if cls._relation_row_type(relation, row_id) == "oa"
        ]
        invoice_row_ids = [
            row_id
            for row_id in row_ids
            if cls._relation_row_type(relation, row_id) == "invoice"
        ]
        bindings: list[dict[str, Any]] = []
        for oa_row_id in oa_row_ids:
            attachment_invoice_row_ids = [
                row_id
                for row_id in invoice_row_ids
                if cls._invoice_row_is_oa_attachment_for_oa(
                    row_id,
                    oa_row_id,
                    row_id_aliases=row_id_aliases,
                )
            ]
            if not attachment_invoice_row_ids:
                continue
            row_ids_for_binding = [oa_row_id, *attachment_invoice_row_ids]
            row_types_for_binding = [
                cls._relation_row_type(relation, row_id)
                for row_id in row_ids_for_binding
            ]
            timestamp = str(relation.get("created_at") or relation.get("updated_at") or cls._timestamp())
            bindings.append(
                cls._normalize_relation(
                    {
                        "case_id": f"CASE-OA-ATT-{oa_row_id}",
                        "row_ids": row_ids_for_binding,
                        "row_types": row_types_for_binding,
                        "status": ACTIVE_PAIR_RELATION_STATUS,
                        "relation_mode": "manual_confirmed",
                        "month_scope": str(relation.get("month_scope") or "all"),
                        "created_by": str(relation.get("created_by") or ""),
                        "note": "OA attachment invoice binding",
                        "amount_check": {},
                        "special_metadata": {
                            "source": "oa_attachment_invoice",
                            "immutable_oa_attachment_binding": True,
                            "contains_immutable_oa_attachment_binding": True,
                            "parent_oa_row_id": oa_row_id,
                        },
                        "created_at": timestamp,
                        "updated_at": str(relation.get("updated_at") or timestamp),
                    },
                    fallback_case_id=f"CASE-OA-ATT-{oa_row_id}",
                )
            )
        return bindings

    @classmethod
    def _append_relation_rows(cls, relation: dict[str, Any], rows_from: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(relation)
        merged_row_ids, merged_row_types = cls._normalize_relation_entries(
            list(merged.get("row_ids") or []),
            list(merged.get("row_types") or []),
        )
        additional_row_ids, additional_row_types = cls._normalize_relation_entries(
            list(rows_from.get("row_ids") or []),
            list(rows_from.get("row_types") or []),
        )
        known_row_ids = set(merged_row_ids)
        for row_id, row_type in zip(additional_row_ids, additional_row_types):
            if row_id in known_row_ids:
                continue
            known_row_ids.add(row_id)
            merged_row_ids.append(row_id)
            merged_row_types.append(row_type)
        merged["row_ids"] = merged_row_ids
        merged["row_types"] = merged_row_types
        return merged

    @classmethod
    def _relation_row_id_set(
        cls,
        relation: dict[str, Any],
        *,
        row_id_aliases: dict[str, str] | None = None,
    ) -> set[str]:
        return {
            cls._canonical_relation_row_id(row_id, row_id_aliases=row_id_aliases)
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        }

    @staticmethod
    def _canonical_relation_row_id(row_id: Any, *, row_id_aliases: dict[str, str] | None = None) -> str:
        value = str(row_id).strip()
        if not value or not row_id_aliases:
            return value
        seen = {value}
        current = value
        while True:
            candidate = str(row_id_aliases.get(current, current)).strip()
            if not candidate or candidate == current or candidate in seen:
                return current
            seen.add(candidate)
            current = candidate

    @classmethod
    def _invoice_row_is_oa_attachment_for_oa(
        cls,
        invoice_row_id: str,
        oa_row_id: str,
        *,
        row_id_aliases: dict[str, str] | None = None,
    ) -> bool:
        invoice_candidates = {
            str(invoice_row_id).strip(),
            cls._canonical_relation_row_id(invoice_row_id, row_id_aliases=row_id_aliases),
        }
        oa_candidates = {
            str(oa_row_id).strip(),
            cls._canonical_relation_row_id(oa_row_id, row_id_aliases=row_id_aliases),
        }
        return any(
            oa_attachment_row_id_matches_oa(invoice_candidate, oa_candidate)
            for invoice_candidate in invoice_candidates
            if invoice_candidate
            for oa_candidate in oa_candidates
            if oa_candidate
        )

    @classmethod
    def _relation_row_type(cls, relation: dict[str, Any], row_id: str) -> str:
        row_ids = [str(value).strip() for value in list(relation.get("row_ids") or [])]
        row_types = [str(value).strip() for value in list(relation.get("row_types") or [])]
        for index, candidate in enumerate(row_ids):
            if candidate != row_id:
                continue
            if index < len(row_types) and row_types[index]:
                return row_types[index]
            break
        return cls._row_type_for_row_id(row_id)

    @classmethod
    def _normalize_history(cls, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [cls._normalize_history_entry(entry) for entry in history if isinstance(entry, dict)]

    @staticmethod
    def _normalize_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(entry)
        normalized["operation_id"] = str(entry.get("operation_id") or uuid4().hex)
        normalized["operation_type"] = str(entry.get("operation_type") or "")
        normalized["before_relations"] = [
            deepcopy(relation) for relation in list(entry.get("before_relations") or []) if isinstance(relation, dict)
        ]
        normalized["after_relations"] = [
            deepcopy(relation) for relation in list(entry.get("after_relations") or []) if isinstance(relation, dict)
        ]
        normalized["affected_row_ids"] = [
            str(row_id).strip()
            for row_id in list(entry.get("affected_row_ids") or [])
            if str(row_id).strip()
        ]
        normalized["note"] = str(entry.get("note") or "")
        amount_check = entry.get("amount_check")
        normalized["amount_check"] = deepcopy(amount_check) if isinstance(amount_check, dict) else {}
        normalized["created_by"] = str(entry.get("created_by") or "")
        normalized["created_at"] = str(entry.get("created_at") or WorkbenchPairRelationService._timestamp())
        return normalized

    def _active_relation_for_any_row_id(self, row_ids: list[str]) -> dict[str, Any] | None:
        for row_id in row_ids:
            relation = self.get_active_relation_by_row_id(str(row_id))
            if isinstance(relation, dict):
                return relation
        return None

    @classmethod
    def _mark_owned_before_relations_restorable(
        cls,
        relations: list[dict[str, Any]] | None,
        active_before_relations: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        active_by_case_id = {
            str(relation.get("case_id") or "").strip(): relation
            for relation in list(active_before_relations or [])
            if isinstance(relation, dict) and str(relation.get("case_id") or "").strip()
        }
        marked_relations: list[dict[str, Any]] = []
        for relation in list(relations or []):
            if not isinstance(relation, dict):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            active_relation = active_by_case_id.get(case_id)
            if (
                isinstance(active_relation, dict)
                and workbench_relations_have_same_row_set(relation, active_relation)
                and relation_mode_can_be_restored_on_withdraw(str(relation.get("relation_mode") or ""))
            ):
                marked_relations.append(mark_relation_restorable_on_withdraw(relation))
            else:
                marked_relations.append(deepcopy(relation))
        return marked_relations

    @classmethod
    def _restorable_relation_snapshots(
        cls,
        relations: list[dict[str, Any]] | None,
        *,
        active_relation: dict[str, Any] | None = None,
        row_id_aliases: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        return [
            deepcopy(relation)
            for relation in list(relations or [])
            if cls._is_restorable_relation_snapshot(
                relation,
                active_relation=active_relation,
                row_id_aliases=row_id_aliases,
            )
        ]

    @staticmethod
    def _is_restorable_relation_snapshot(
        relation: dict[str, Any],
        *,
        active_relation: dict[str, Any] | None = None,
        row_id_aliases: dict[str, str] | None = None,
    ) -> bool:
        return is_workbench_relation_snapshot_restorable(
            relation,
            active_relation=active_relation,
            row_id_aliases=row_id_aliases,
        )

    def _latest_confirm_history_for_relation(self, relation: dict[str, Any]) -> dict[str, Any] | None:
        case_id = str(relation.get("case_id", "")).strip()
        row_ids = {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}
        for history in reversed(self._pair_relation_history):
            if str(history.get("operation_type")) not in WITHDRAW_RESTORABLE_CONFIRM_OPERATION_TYPES:
                continue
            for after_relation in list(history.get("after_relations") or []):
                if not isinstance(after_relation, dict):
                    continue
                after_case_id = str(after_relation.get("case_id", "")).strip()
                after_row_ids = {
                    str(row_id).strip()
                    for row_id in list(after_relation.get("row_ids") or [])
                    if str(row_id).strip()
                }
                if after_case_id == case_id or (row_ids and row_ids.issubset(after_row_ids)):
                    return deepcopy(history)
        return None

    @staticmethod
    def _history_touches_cases(history: dict[str, Any], case_ids: set[str]) -> bool:
        if not case_ids:
            return False
        for key in ("case_id", "relation_case_id"):
            if str(history.get(key) or "").strip() in case_ids:
                return True
        for collection_key in ("before_relations", "after_relations"):
            for relation in list(history.get(collection_key) or []):
                if isinstance(relation, dict) and str(relation.get("case_id") or "").strip() in case_ids:
                    return True
        return False

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
