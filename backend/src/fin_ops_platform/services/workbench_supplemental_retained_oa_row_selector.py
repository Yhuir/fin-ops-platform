from __future__ import annotations

from typing import Callable


class WorkbenchSupplementalRetainedOaRowSelector:
    """Selects retained OA row ids from manual choices and bank-linked relations."""

    def __init__(
        self,
        *,
        manual_retained_oa_row_ids: Callable[[], list[str]],
        relation_read_port: object,
        resolve_live_rows: Callable[[list[str]], list[dict[str, object]]],
        row_is_on_or_after: Callable[..., bool],
    ) -> None:
        self._manual_retained_oa_row_ids = manual_retained_oa_row_ids
        self._relation_read_port = relation_read_port
        self._resolve_live_rows = resolve_live_rows
        self._row_is_on_or_after = row_is_on_or_after

    def select(self, cutoff_date: object) -> list[str]:
        retained_row_ids: set[str] = set(self._manual_retained_oa_row_ids())
        list_active_relations = getattr(self._relation_read_port, "list_active_relations", None)
        if not callable(list_active_relations):
            return sorted(retained_row_ids)
        for relation in list_active_relations():
            if not isinstance(relation, dict):
                continue
            row_ids = [
                str(row_id).strip()
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            ]
            row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
            oa_row_ids = [
                row_id
                for index, row_id in enumerate(row_ids)
                if (row_types[index] if index < len(row_types) else "") == "oa"
            ]
            bank_row_ids = [
                row_id
                for index, row_id in enumerate(row_ids)
                if (row_types[index] if index < len(row_types) else "") == "bank"
            ]
            if not oa_row_ids or not bank_row_ids:
                continue
            try:
                bank_rows = self._resolve_live_rows(bank_row_ids)
            except KeyError:
                continue
            if any(self._row_is_on_or_after(row, cutoff_date, row_type="bank") for row in bank_rows):
                retained_row_ids.update(oa_row_ids)
        return sorted(retained_row_ids)
