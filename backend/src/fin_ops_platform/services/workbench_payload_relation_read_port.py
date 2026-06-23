from __future__ import annotations

from typing import Any


class WorkbenchPayloadRelationReadPort:
    def __init__(self, relation_reader: Any) -> None:
        self._relation_reader = relation_reader

    def get_active_relation_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        get_active_relation_by_row_id = getattr(self._relation_reader, "get_active_relation_by_row_id", None)
        if not callable(get_active_relation_by_row_id):
            raise ValueError("relation_reader must provide get_active_relation_by_row_id(...).")
        relation = get_active_relation_by_row_id(str(row_id or ""))
        if relation is None:
            return None
        if not isinstance(relation, dict):
            raise ValueError("relation_reader returned a non-dict active relation.")
        return dict(relation)

    def list_active_relations(self) -> list[dict[str, Any]]:
        list_active_relations = getattr(self._relation_reader, "list_active_relations", None)
        if not callable(list_active_relations):
            raise ValueError("relation_reader must provide list_active_relations().")
        relations = list(list_active_relations() or [])
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError("relation_reader returned a non-dict active relation.")
        return [dict(relation) for relation in relations]
