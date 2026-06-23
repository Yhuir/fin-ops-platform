from __future__ import annotations

from typing import Any


class WorkbenchConfirmLinkContextRelationReadPort:
    def __init__(self, relation_reader: Any) -> None:
        self._relation_reader = relation_reader

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        active_relations_for_row_ids = getattr(self._relation_reader, "active_relations_for_row_ids", None)
        if not callable(active_relations_for_row_ids):
            raise ValueError("relation_reader must provide active_relations_for_row_ids().")
        relations = list(active_relations_for_row_ids(list(row_ids or [])) or [])
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError("relation_reader returned a non-dict active relation.")
        return [dict(relation) for relation in relations]
