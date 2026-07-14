from __future__ import annotations

from typing import Any

from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


class BankDetailsRelationTagProjectionService:
    def __init__(
        self,
        *,
        relation_facade: WorkbenchRelationReadFacade | None = None,
    ) -> None:
        self._relation_facade = relation_facade
        self._index_cache_key = ""
        self._index_cache: dict[str, dict[str, Any]] = {}

    def clear_cache(self) -> None:
        self._index_cache_key = ""
        self._index_cache = {}

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
        return self._relation_tags_from_distribution(normalized_ids)

    def _relation_tags_from_distribution(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        if self._relation_facade is None:
            return {}
        get_by_row_ids = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(get_by_row_ids):
            return {}
        payload = get_by_row_ids(
            transaction_ids,
            require_fresh=False,
            reason="bank_details_relation_tag_projection",
        )
        result: dict[str, dict[str, Any]] = {}
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("row_id") or "").strip()
            if row_id not in transaction_ids:
                continue
            relation_status = str(row.get("relation_status") or "linked").strip() or "linked"
            if relation_status != "linked":
                continue
            row_types = {"bank"}
            if list(row.get("linked_oa") or []):
                row_types.add("oa")
            if list(row.get("linked_input_invoices") or []) or list(row.get("linked_output_invoices") or []):
                row_types.add("invoice")
            case_id = next((str(group_id).strip() for group_id in list(row.get("group_ids") or []) if str(group_id).strip()), "")
            if case_id or len(row_types) > 1:
                result[row_id] = {"case_id": case_id, "row_types": sorted(row_types), "relation_status": "linked"}
        return result
