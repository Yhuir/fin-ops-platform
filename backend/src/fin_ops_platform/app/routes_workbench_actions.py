from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.workbench_anomaly_review_service import (
    WorkbenchAnomalyReviewConflict,
    WorkbenchAnomalyReviewService,
)
from fin_ops_platform.services.workbench_idempotency import (
    WorkbenchIdempotencyFailed,
    WorkbenchIdempotencyInProgress,
    WorkbenchIdempotencyKeyConflict,
)
from fin_ops_platform.services.workbench_invoice_expense_item_assignment_service import (
    WorkbenchInvoiceExpenseItemAssignmentError,
)
from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict


class WorkbenchActionApiRoutes:
    """Modern Workbench action route owner backed by facade/application services."""

    def __init__(
        self,
        *,
        write_facade_provider: Callable[[], Any],
        anomaly_review_service: WorkbenchAnomalyReviewService | None = None,
        invoice_expense_item_assignment_service_provider: Callable[[], Any] | None = None,
    ) -> None:
        self._write_facade_provider = write_facade_provider
        self._anomaly_review_service = anomaly_review_service
        self._invoice_expense_item_assignment_service_provider = (
            invoice_expense_item_assignment_service_provider
        )

    def assign_invoice_expense_items(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
        tenant_id: str,
        request_id: str,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        provider = self._invoice_expense_item_assignment_service_provider
        if provider is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "invoice_expense_item_assignment_unavailable",
                "message": "发票明细归属服务暂时不可用。",
            }
        try:
            service = provider()
        except RuntimeError:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "invoice_expense_item_assignment_unavailable",
                "message": "发票明细归属服务暂时不可用。",
            }
        try:
            result = service.assign(
                payload,
                actor_id=actor_id,
                tenant_id=tenant_id,
                request_id=request_id,
            )
        except WorkbenchInvoiceExpenseItemAssignmentError as exc:
            return HTTPStatus(exc.status_code), {
                "error": exc.code,
                "message": exc.message,
            }
        except (
            WorkbenchIdempotencyFailed,
            WorkbenchIdempotencyInProgress,
            WorkbenchIdempotencyKeyConflict,
        ) as exc:
            return HTTPStatus(exc.status_code), exc.to_response_payload()
        except WorkbenchWriteConflict as exc:
            conflict_payload = exc.to_response_payload()
            return HTTPStatus(exc.status_code), dict(conflict_payload["payload"])
        return HTTPStatus.OK, dict(result)

    def review_anomaly(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        if self._anomaly_review_service is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "workbench_anomaly_review_service_unavailable",
                "message": "异常审阅服务暂时不可用。",
            }
        try:
            result = self._anomaly_review_service.review(payload, actor_id=actor_id)
        except WorkbenchAnomalyReviewConflict as error:
            return HTTPStatus.CONFLICT, {
                "error": error.code,
                "message": str(error),
            }
        except ValueError as error:
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_anomaly_review_request",
                "message": str(error),
            }
        return HTTPStatus.OK, result

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

    def confirm_personal_advance_repayment(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> Any:
        return self._write_facade_provider().confirm_personal_advance_repayment(payload, request_id=request_id)
