from __future__ import annotations

from typing import Any


class WorkbenchOaInvoiceOffsetRelationReadPort:
    def __init__(self, relation_reader: Any) -> None:
        self._relation_reader = relation_reader

    def active_relations_for_mode(self, relation_mode: str) -> list[dict[str, Any]]:
        list_active_relations = getattr(self._relation_reader, "list_active_relations", None)
        if not callable(list_active_relations):
            raise ValueError("relation_reader must provide list_active_relations().")
        target_mode = str(relation_mode or "").strip()
        relations = list(list_active_relations() or [])
        result: list[dict[str, Any]] = []
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError("relation_reader returned a non-dict active relation.")
            if str(relation.get("relation_mode") or "").strip() == target_mode:
                result.append(dict(relation))
        return result
