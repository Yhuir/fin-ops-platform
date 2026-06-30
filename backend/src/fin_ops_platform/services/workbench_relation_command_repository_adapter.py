from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchRelationCommandRepositoryAdapter:
    def __init__(
        self,
        *,
        pair_relation_service: WorkbenchPairRelationService,
        repository: Any | None = None,
        after_apply: Callable[[], None] | None = None,
        save_repository: bool = True,
    ) -> None:
        self._pair_relation_service = pair_relation_service
        self._repository = repository
        self._after_apply = after_apply
        self._save_repository = bool(save_repository)

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        loader = getattr(self._repository, "load_workbench_pair_relations", None)
        if callable(loader):
            snapshot = loader()
            return deepcopy(snapshot) if isinstance(snapshot, dict) else {}
        return self._pair_relation_service.snapshot()

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | list[str] | None = None,
    ) -> None:
        normalized_case_ids = [
            str(case_id).strip()
            for case_id in list(changed_case_ids or [])
            if str(case_id).strip()
        ]
        saver = getattr(self._repository, "save_workbench_pair_relations", None)
        if self._save_repository and callable(saver):
            saver(snapshot, changed_case_ids=normalized_case_ids)
        self._apply_snapshot(snapshot, changed_case_ids=normalized_case_ids)

    def _apply_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: list[str],
    ) -> None:
        changed_ids = {
            str(case_id).strip()
            for case_id in list(changed_case_ids or [])
            if str(case_id).strip()
        }
        current = self._pair_relation_service.snapshot()
        current_relations = dict(current.get("pair_relations") if isinstance(current.get("pair_relations"), dict) else {})
        incoming_relations = dict(snapshot.get("pair_relations") if isinstance(snapshot.get("pair_relations"), dict) else {})
        if changed_ids:
            for case_id in changed_ids:
                if case_id in incoming_relations:
                    current_relations[case_id] = deepcopy(incoming_relations[case_id])
                else:
                    current_relations.pop(case_id, None)
        else:
            current_relations.update(deepcopy(incoming_relations))

        current_history = [
            deepcopy(history)
            for history in list(current.get("pair_relation_history") or [])
            if isinstance(history, dict) and not self._relation_history_touches_cases(history, changed_ids)
        ]
        incoming_history = [
            deepcopy(history)
            for history in list(snapshot.get("pair_relation_history") or [])
            if isinstance(history, dict)
        ]
        merged_snapshot: dict[str, Any] = {"pair_relations": current_relations}
        if current_history or incoming_history:
            merged_snapshot["pair_relation_history"] = [*current_history, *incoming_history]
        merged_service = WorkbenchPairRelationService.from_snapshot(merged_snapshot)
        self._pair_relation_service._pair_relations = deepcopy(merged_service._pair_relations)
        self._pair_relation_service._pair_relation_history = deepcopy(merged_service._pair_relation_history)
        if self._after_apply is not None:
            self._after_apply()

    @staticmethod
    def _relation_history_touches_cases(history: dict[str, Any], case_ids: set[str]) -> bool:
        if not case_ids:
            return False
        for key in ("before_relations", "after_relations"):
            for relation in list(history.get(key) or []):
                if isinstance(relation, dict) and str(relation.get("case_id") or "").strip() in case_ids:
                    return True
        return False
