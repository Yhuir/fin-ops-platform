from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchRelationCommandRepositoryAdapter:
    def __init__(
        self,
        *,
        pair_relation_service: WorkbenchPairRelationService,
        repository: Any | None = None,
        save_repository: bool = True,
    ) -> None:
        self._pair_relation_service = pair_relation_service
        self._repository = repository
        self._save_repository = bool(save_repository)

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        loader = getattr(self._repository, "load_workbench_pair_relations", None)
        if callable(loader):
            snapshot = loader()
            return deepcopy(snapshot) if isinstance(snapshot, dict) else {}
        return self._pair_relation_service.snapshot()

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        loader = getattr(self._repository, "load_workbench_pair_relations_for_row_ids", None)
        if callable(loader):
            snapshot = loader(list(row_ids or []), case_ids=list(case_ids or []))
            return deepcopy(snapshot) if isinstance(snapshot, dict) else {}
        return WorkbenchPairRelationService.from_snapshot(
            self.load_workbench_pair_relations()
        ).snapshot_for_row_ids(list(row_ids or []), case_ids=list(case_ids or []))

    def load_active_workbench_pair_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        normalized_case_id = str(case_id or "").strip()
        if not normalized_case_id:
            return None
        loader = getattr(self._repository, "load_active_workbench_pair_relation_by_case_id", None)
        if callable(loader):
            relation = loader(normalized_case_id)
            return deepcopy(relation) if isinstance(relation, dict) else None
        return self._pair_relation_service.get_active_relation_by_case_id(normalized_case_id)

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

    def acquire_relation_member_locks(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> list[str]:
        acquire = getattr(self._repository, "acquire_relation_member_locks", None)
        if callable(acquire):
            return list(
                acquire(
                    list(row_ids or []),
                    row_types=list(row_types or []),
                    case_ids=list(case_ids or []),
                )
                or []
            )
        normalized_types = [str(item).strip() for item in list(row_types or [])]
        return sorted(
            f"{normalized_types[index] if index < len(normalized_types) else 'unknown'}:{row_id}"
            for index, row_id in enumerate(str(item).strip() for item in list(row_ids or []))
            if row_id
        )

    def _apply_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: list[str],
    ) -> None:
        self._pair_relation_service.apply_snapshot_delta(
            snapshot,
            changed_case_ids=changed_case_ids,
        )
