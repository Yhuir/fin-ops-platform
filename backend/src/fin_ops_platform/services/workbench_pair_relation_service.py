from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any


ACTIVE_PAIR_RELATION_STATUS = "active"
CANCELLED_PAIR_RELATION_STATUS = "cancelled"


class WorkbenchPairRelationService:
    def __init__(self, *, pair_relations: dict[str, dict[str, Any]] | None = None) -> None:
        self._pair_relations = self._normalize_pair_relations(pair_relations or {})

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchPairRelationService":
        if not snapshot:
            return cls()
        pair_relations = snapshot.get("pair_relations")
        return cls(pair_relations=pair_relations if isinstance(pair_relations, dict) else {})

    def snapshot(self) -> dict[str, Any]:
        return {"pair_relations": deepcopy(self._pair_relations)}

    def snapshot_case_ids(self, case_ids: list[str]) -> dict[str, Any]:
        normalized_case_ids = {
            str(case_id).strip()
            for case_id in list(case_ids or [])
            if str(case_id).strip()
        }
        return {
            "pair_relations": {
                case_id: deepcopy(relation)
                for case_id, relation in self._pair_relations.items()
                if case_id in normalized_case_ids
            }
        }

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
        normalized["created_at"] = str(relation.get("created_at") or cls._timestamp())
        normalized["updated_at"] = str(relation.get("updated_at") or normalized["created_at"])
        return normalized

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
