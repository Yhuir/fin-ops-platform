from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.workbench_exception_application_service import WorkbenchExceptionApplicationService
from fin_ops_platform.services.workbench_amount_mismatch_exception_service import (
    WorkbenchAmountMismatchConflict,
    WorkbenchAmountMismatchExceptionService,
)
from fin_ops_platform.services.workbench_read_model_version import WorkbenchReadModelVersionConflictError


class WorkbenchActionApiRoutes:
    """Modern Workbench action route owner backed by facade/application services."""

    def __init__(
        self,
        *,
        exception_service: WorkbenchExceptionApplicationService,
        write_facade_provider: Callable[[], Any],
        amount_mismatch_service: WorkbenchAmountMismatchExceptionService | None = None,
    ) -> None:
        self._exception_service = exception_service
        self._write_facade_provider = write_facade_provider
        self._amount_mismatch_service = amount_mismatch_service

    def set_amount_mismatch_ignored(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
        ignored: bool,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        if self._amount_mismatch_service is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "workbench_amount_mismatch_service_unavailable",
                "message": "金额异常处理服务暂时不可用。",
            }
        try:
            result = self._amount_mismatch_service.set_ignored(
                payload,
                actor_id=actor_id,
                ignored=ignored,
            )
        except WorkbenchReadModelVersionConflictError as error:
            return HTTPStatus.CONFLICT, {
                "error": "workbench_read_model_version_conflict",
                "message": "关联台数据已变化，请刷新后重试。",
                "expected_read_model_version": error.expected,
                "read_model_version": error.current,
            }
        except WorkbenchAmountMismatchConflict as error:
            return HTTPStatus.CONFLICT, {
                "error": "workbench_amount_mismatch_changed",
                "message": str(error),
            }
        except ValueError as error:
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_amount_mismatch_request",
                "message": str(error),
            }
        return HTTPStatus.OK, result

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
            result = self._write_facade_provider().preview_confirm_link(payload)
        except KeyError as exc:
            row_id = str(exc.args[0]).strip() if exc.args else ""
            return HTTPStatus.BAD_REQUEST, {
                "error": "workbench_row_not_found",
                "message": "所选关联台记录不可用，请刷新后重试。",
                "row_id": row_id,
            }
        except (TypeError, ValueError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_confirm_link_preview_request",
                "message": str(exc),
            }
        return HTTPStatus(result.status_code), dict(result.payload)

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

    def withdraw_link_preview(self, payload: dict[str, Any]) -> Any:
        return self._write_facade_provider().preview_withdraw_link(payload)

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
