from __future__ import annotations

from typing import Any, Callable


class WorkbenchRelationCaseIdAllocator:
    def __init__(
        self,
        *,
        relation_snapshot_provider: Callable[[], dict[str, Any]],
        next_case_id: Callable[[], str],
        max_attempts: int = 10000,
    ) -> None:
        self._relation_snapshot_provider = relation_snapshot_provider
        self._next_case_id = next_case_id
        self._max_attempts = int(max_attempts or 0)

    def next_case_id(self) -> str:
        used_case_ids = self._used_case_ids()
        for _attempt in range(self._max_attempts):
            case_id = str(self._next_case_id() or "").strip()
            if case_id and case_id not in used_case_ids:
                return case_id
        raise RuntimeError("Unable to allocate an unused workbench relation case id.")

    def _used_case_ids(self) -> set[str]:
        snapshot = self._relation_snapshot_provider()
        relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else {}
        return {
            str(case_id).strip()
            for case_id in (relations.keys() if isinstance(relations, dict) else [])
            if str(case_id).strip()
        }
