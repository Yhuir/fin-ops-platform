from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchExceptionRollbackRestoreService:
    def __init__(
        self,
        *,
        state_store: Any | None,
        replace_exception_case_service: Callable[[WorkbenchExceptionCaseService], None],
        replace_pair_relation_service: Callable[[WorkbenchPairRelationService], None],
        replace_override_service: Callable[[WorkbenchOverrideService], None],
        configure_exception_application_service: Callable[[], None],
    ) -> None:
        self._state_store = state_store
        self._replace_exception_case_service = replace_exception_case_service
        self._replace_pair_relation_service = replace_pair_relation_service
        self._replace_override_service = replace_override_service
        self._configure_exception_application_service = configure_exception_application_service

    def restore_write_snapshots(
        self,
        *,
        previous_exception_snapshot: dict[str, object],
        previous_pair_snapshot: dict[str, object],
        previous_override_snapshot: dict[str, object],
    ) -> None:
        self._replace_exception_case_service(WorkbenchExceptionCaseService.from_snapshot(previous_exception_snapshot))
        self._replace_pair_relation_service(WorkbenchPairRelationService.from_snapshot(previous_pair_snapshot))
        self._replace_override_service(WorkbenchOverrideService.from_snapshot(previous_override_snapshot))
        self._configure_exception_application_service()

    def restore_pair_snapshots(
        self,
        *,
        previous_exception_snapshot: dict[str, object],
        previous_pair_snapshot: dict[str, object],
    ) -> None:
        self._replace_exception_case_service(WorkbenchExceptionCaseService.from_snapshot(previous_exception_snapshot))
        self._replace_pair_relation_service(WorkbenchPairRelationService.from_snapshot(previous_pair_snapshot))
        self._configure_exception_application_service()

    def restore_override_snapshots(
        self,
        *,
        previous_exception_snapshot: dict[str, object],
        previous_override_snapshot: dict[str, object],
    ) -> None:
        if self._state_store is not None:
            try:
                self._state_store.save_workbench_exception_cases(previous_exception_snapshot)
            except Exception:
                pass
        self._replace_exception_case_service(WorkbenchExceptionCaseService.from_snapshot(previous_exception_snapshot))
        self._replace_override_service(WorkbenchOverrideService.from_snapshot(previous_override_snapshot))
