from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


ACTIVE_PAIR_RELATION_STATUS = "active"
CANCELLED_PAIR_RELATION_STATUS = "cancelled"


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

    def snapshot_case_ids(self, case_ids: list[str]) -> dict[str, Any]:
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
        if self._pair_relation_history:
            payload["pair_relation_history"] = deepcopy(self._pair_relation_history)
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
    ) -> dict[str, Any]:
        resolved_case_id = str(case_id).strip()
        if not resolved_case_id:
            raise ValueError("case_id is required for pair relation creation.")

        timestamp = created_at or self._timestamp()
        existing_relation = self._pair_relations.get(resolved_case_id)
        relation = self._normalize_relation(
            {
                **(deepcopy(existing_relation) if isinstance(existing_relation, dict) else {}),
                "case_id": resolved_case_id,
                "row_ids": list(row_ids),
                "row_types": list(row_types),
                "status": ACTIVE_PAIR_RELATION_STATUS,
                "relation_mode": relation_mode,
                "month_scope": month_scope,
                "created_by": created_by,
                "note": str(note).strip() if note is not None else "",
                "amount_check": deepcopy(amount_check) if isinstance(amount_check, dict) else {},
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
        created_at: str | None = None,
        before_relations: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        active_before_relations = self.active_relations_for_row_ids(row_ids)
        history_before_relations = (
            [deepcopy(relation) for relation in before_relations if isinstance(relation, dict)]
            if before_relations is not None
            else active_before_relations
        )
        timestamp = created_at or self._timestamp()
        for relation in active_before_relations:
            self.cancel_relation(str(relation.get("case_id", "")), cancelled_at=timestamp)
        after_relation = self.create_active_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=row_types,
            relation_mode=relation_mode,
            created_by=created_by,
            month_scope=month_scope,
            created_at=timestamp,
            note=note,
            amount_check=amount_check,
        )
        history = self.record_history(
            operation_type="confirm_link",
            before_relations=history_before_relations,
            after_relations=[after_relation],
            affected_row_ids=row_ids,
            created_by=created_by,
            note=note,
            amount_check=amount_check,
            created_at=timestamp,
        )
        return after_relation, history

    def preview_withdraw_for_row_ids(self, row_ids: list[str]) -> dict[str, Any]:
        active_relation = self._active_relation_for_any_row_id(row_ids)
        if not isinstance(active_relation, dict):
            raise KeyError("workbench_pair_relation_not_found")
        confirm_history = self._latest_confirm_history_for_relation(active_relation)
        return {
            "active_relation": deepcopy(active_relation),
            "confirm_history": deepcopy(confirm_history) if isinstance(confirm_history, dict) else {},
            "before_relations": [deepcopy(active_relation)],
            "after_relations": deepcopy(confirm_history.get("before_relations") or []) if isinstance(confirm_history, dict) else [],
        }

    def withdraw_latest_for_row_ids(
        self,
        row_ids: list[str],
        *,
        created_by: str,
        note: str | None = None,
        created_at: str | None = None,
        fallback_after_relations: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        preview = self.preview_withdraw_for_row_ids(row_ids)
        active_relation = preview["active_relation"]
        restored_relations = list(preview["after_relations"])
        if not restored_relations and fallback_after_relations:
            restored_relations = [
                deepcopy(relation)
                for relation in fallback_after_relations
                if isinstance(relation, dict)
            ]
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
        normalized["row_ids"] = [
            str(value).strip()
            for value in list(relation.get("row_ids") or [])
            if str(value).strip()
        ]
        normalized["row_types"] = [
            str(value).strip()
            for value in list(relation.get("row_types") or [])
            if str(value).strip()
        ]
        normalized["status"] = str(relation.get("status") or ACTIVE_PAIR_RELATION_STATUS)
        normalized["relation_mode"] = str(relation.get("relation_mode") or "manual_confirmed")
        normalized["month_scope"] = str(relation.get("month_scope") or "all")
        created_by = relation.get("created_by")
        normalized["created_by"] = "" if created_by is None else str(created_by)
        normalized["note"] = str(relation.get("note") or "")
        amount_check = relation.get("amount_check")
        normalized["amount_check"] = deepcopy(amount_check) if isinstance(amount_check, dict) else {}
        normalized["created_at"] = str(relation.get("created_at") or cls._timestamp())
        normalized["updated_at"] = str(relation.get("updated_at") or normalized["created_at"])
        return normalized

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

    def _latest_confirm_history_for_relation(self, relation: dict[str, Any]) -> dict[str, Any] | None:
        case_id = str(relation.get("case_id", "")).strip()
        row_ids = {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}
        for history in reversed(self._pair_relation_history):
            if str(history.get("operation_type")) != "confirm_link":
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
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
