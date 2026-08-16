from __future__ import annotations

from typing import Callable

from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchExceptionRollbackRestoreService:
    def __init__(
        self,
        *,
        replace_exception_case_service: Callable[[WorkbenchExceptionCaseService], None],
        replace_pair_relation_service: Callable[[WorkbenchPairRelationService], None],
    ) -> None:
        self._replace_exception_case_service = replace_exception_case_service
        self._replace_pair_relation_service = replace_pair_relation_service

    def restore_pair_snapshots(
        self,
        *,
        previous_exception_snapshot: dict[str, object],
        previous_pair_snapshot: dict[str, object],
    ) -> None:
        self._replace_exception_case_service(WorkbenchExceptionCaseService.from_snapshot(previous_exception_snapshot))
        self._replace_pair_relation_service(WorkbenchPairRelationService.from_snapshot(previous_pair_snapshot))
