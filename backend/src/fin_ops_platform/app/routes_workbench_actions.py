from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fin_ops_platform.services.workbench_exception_application_service import WorkbenchExceptionApplicationService


class WorkbenchActionApiRoutes:
    """Modern Workbench action route owner backed by facade/application services."""

    def __init__(self, *, exception_service: WorkbenchExceptionApplicationService) -> None:
        self._exception_service = exception_service

    def exception_preview(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            preview = self._exception_service.preview(payload)
        except KeyError as exc:
            return HTTPStatus.NOT_FOUND, {"error": "workbench_row_not_found", "message": str(exc)}
        except (TypeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_exception_preview_request",
                "message": str(exc),
            }
        return HTTPStatus.OK, preview
