from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.workbench_exception_application_service import WorkbenchExceptionApplicationService


class WorkbenchActionApiRoutes:
    """Modern Workbench action route owner backed by facade/application services."""

    def __init__(
        self,
        *,
        exception_service: WorkbenchExceptionApplicationService,
        write_facade_provider: Callable[[], Any],
    ) -> None:
        self._exception_service = exception_service
        self._write_facade_provider = write_facade_provider

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

    def exception_apply(self, payload: dict[str, Any], *, request_id: str | None = None) -> Any:
        return self._write_facade_provider().apply_exception(
            payload,
            actor=str(payload.get("actor") or payload.get("confirmed_by") or "system"),
            request_id=request_id,
            action_name="exception_apply",
        )

    def confirm_link_preview(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            preview = self._write_facade_provider().preview_confirm_link(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_confirm_link_preview_request",
                "message": str(exc),
            }
        return HTTPStatus.OK, preview

    def confirm_link(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().confirm_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

    def mark_exception(self, payload: dict[str, Any]) -> Any:
        return self._write_facade_provider().mark_exception(payload)

    def cancel_link(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().cancel_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

    def withdraw_link(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().withdraw_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

    def confirm_cash_pass_through(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().confirm_cash_pass_through(payload, request_id=request_id)

    def confirm_cash_ticket_purchase(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().confirm_cash_ticket_purchase(payload, request_id=request_id)

    def cancel_cash_special(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().cancel_cash_special(payload, request_id=request_id)

    def update_bank_exception(self, payload: dict[str, Any]) -> Any:
        return self._write_facade_provider().update_bank_exception(payload)

    def oa_bank_exception(self, payload: dict[str, Any]) -> Any:
        return self._write_facade_provider().oa_bank_exception(payload)

    def confirm_personal_advance_repayment(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().confirm_personal_advance_repayment(payload, request_id=request_id)

    def cancel_exception(self, payload: dict[str, Any]) -> Any:
        return self._write_facade_provider().cancel_exception(payload)

    def ignore_row(self, payload: dict[str, Any]) -> Any:
        return self._write_facade_provider().ignore_row(payload)

    def unignore_row(self, payload: dict[str, Any]) -> Any:
        return self._write_facade_provider().unignore_row(payload)
