from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchPairRelationRollbackRestoreService:
    def __init__(
        self,
        *,
        state_store: Any | None,
        replace_pair_relation_service: Callable[[WorkbenchPairRelationService], None],
    ) -> None:
        self._state_store = state_store
        self._replace_pair_relation_service = replace_pair_relation_service

    def restore(
        self,
        snapshot: dict[str, object],
        *,
        changed_case_ids: list[str],
    ) -> None:
        restored_service = WorkbenchPairRelationService.from_snapshot(snapshot)
        self._replace_pair_relation_service(restored_service)
        if self._state_store is None:
            return
        try:
            self._state_store.save_workbench_pair_relations(
                snapshot,
                changed_case_ids=changed_case_ids,
            )
        except Exception:
            pass
