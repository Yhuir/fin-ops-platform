from __future__ import annotations

from typing import Any


class BankDetailsRelationTagProjectionService:
    def __init__(
        self,
        *,
        relation_reader: Any | None = None,
    ) -> None:
        self._relation_reader = relation_reader

    def relation_tag_for_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        resolved_transaction_id = str(transaction_id or "").strip()
        if not resolved_transaction_id:
            return None
        return self.relation_tags_for_transactions([resolved_transaction_id]).get(resolved_transaction_id)

    def relation_tags_for_transactions(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = [
            str(transaction_id).strip()
            for transaction_id in list(transaction_ids or [])
            if str(transaction_id).strip()
        ]
        if not normalized_ids:
            return {}
        return self._relation_tags_from_canonical_relations(normalized_ids)

    def _relation_tags_from_canonical_relations(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        if self._relation_reader is None:
            return {}
        active_relations = getattr(self._relation_reader, "active_relations_for_row_ids", None)
        if not callable(active_relations):
            return {}
        result: dict[str, dict[str, Any]] = {}
        transaction_id_set = set(transaction_ids)
        for relation in list(active_relations(transaction_ids) or []):
            if not isinstance(relation, dict) or str(relation.get("status") or "active") != "active":
                continue
            row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
            normalized_types = {row_type for row_type in row_types if row_type}
            case_id = str(relation.get("case_id") or "").strip()
            for row_id in transaction_id_set.intersection(row_ids):
                result[row_id] = {
                    "case_id": case_id,
                    "row_types": sorted(normalized_types),
                    "relation_status": "linked",
                }
        return result
