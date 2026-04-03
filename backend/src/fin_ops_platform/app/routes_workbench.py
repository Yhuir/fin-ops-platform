from __future__ import annotations

from fin_ops_platform.services.workbench_action_service import WorkbenchActionService
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


class WorkbenchApiRoutes:
    def __init__(self, query_service: WorkbenchQueryService, action_service: WorkbenchActionService) -> None:
        self._query_service = query_service
        self._action_service = action_service

    def get_workbench(self, month: str) -> dict[str, object]:
        return self._query_service.get_workbench(month)

    def get_row_detail(self, row_id: str) -> dict[str, object]:
        return {"row": self._query_service.get_row_detail(row_id)}

    def confirm_link(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.confirm_link(
            month=str(payload["month"]),
            row_ids=list(payload["row_ids"]),
            case_id=str(payload["case_id"]) if payload.get("case_id") is not None else None,
        )

    def mark_exception(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.mark_exception(
            month=str(payload["month"]),
            row_id=str(payload["row_id"]),
            exception_code=str(payload["exception_code"]),
            comment=str(payload.get("comment")) if payload.get("comment") is not None else None,
        )

    def cancel_link(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.cancel_link(
            month=str(payload["month"]),
            row_id=str(payload["row_id"]),
            comment=str(payload.get("comment")) if payload.get("comment") is not None else None,
        )

    def update_bank_exception(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.update_bank_exception(
            month=str(payload["month"]),
            row_id=str(payload["row_id"]),
            relation_code=str(payload["relation_code"]),
            relation_label=str(payload["relation_label"]),
            comment=str(payload.get("comment")) if payload.get("comment") is not None else None,
        )
