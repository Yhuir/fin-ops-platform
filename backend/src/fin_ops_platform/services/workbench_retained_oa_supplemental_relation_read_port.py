from __future__ import annotations

from typing import Any


class WorkbenchRetainedOaSupplementalRelationReadPort:
    def __init__(self, relation_reader: Any) -> None:
        self._relation_reader = relation_reader

    def list_active_relations(self) -> list[dict[str, Any]]:
        list_active_relations = getattr(self._relation_reader, "list_active_relations", None)
        if not callable(list_active_relations):
            raise ValueError("relation_reader must provide list_active_relations().")
        relations = list(list_active_relations() or [])
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError("relation_reader returned a non-dict active relation.")
        return [dict(relation) for relation in relations]
