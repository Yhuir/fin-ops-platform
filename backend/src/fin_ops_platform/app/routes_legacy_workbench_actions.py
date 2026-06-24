from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.reconciliation import ManualReconciliationService


class LegacyWorkbenchActionRoutes:
    """Compat-only owner for pre-API Workbench ledger action endpoints."""

    def __init__(
        self,
        *,
        reconciliation_service: ManualReconciliationService,
        ledger_service: LedgerReminderService,
    ) -> None:
        self._reconciliation_service = reconciliation_service
        self._ledger_service = ledger_service

    def confirm(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            actor_id = str(payload["actor_id"])
            invoice_ids = list(payload["invoice_ids"])
            transaction_ids = list(payload["transaction_ids"])
        except (KeyError, TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_confirm_request",
                "message": "actor_id, invoice_ids and transaction_ids are required.",
            }

        try:
            case = self._reconciliation_service.confirm_manual_reconciliation(
                actor_id=actor_id,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                oa_ids=list(payload.get("oa_ids", [])),
                source_result_id=payload.get("source_result_id"),
                remark=payload.get("remark"),
                amount=payload.get("amount"),
            )
        except KeyError as exc:
            return HTTPStatus.NOT_FOUND, {"error": "reconciliation_object_not_found", "message": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_workbench_confirm_request", "message": str(exc)}
        ledgers = self._ledger_service.sync_from_case(case)
        return HTTPStatus.OK, {"case": case, "ledgers": ledgers}

    def difference(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            actor_id = str(payload["actor_id"])
            invoice_ids = list(payload["invoice_ids"])
            transaction_ids = list(payload["transaction_ids"])
            difference_reason = str(payload["difference_reason"])
        except (KeyError, TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_difference_request",
                "message": "actor_id, invoice_ids, transaction_ids and difference_reason are required.",
            }

        try:
            case = self._reconciliation_service.confirm_difference_reconciliation(
                actor_id=actor_id,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                difference_reason=difference_reason,
                difference_note=payload.get("difference_note"),
                oa_ids=list(payload.get("oa_ids", [])),
                source_result_id=payload.get("source_result_id"),
            )
        except KeyError as exc:
            return HTTPStatus.NOT_FOUND, {"error": "reconciliation_object_not_found", "message": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_workbench_difference_request", "message": str(exc)}
        return HTTPStatus.OK, {"case": case}

    def exception(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            actor_id = str(payload["actor_id"])
            biz_side = str(payload["biz_side"])
            exception_code = str(payload["exception_code"])
            invoice_ids = list(payload.get("invoice_ids", []))
            transaction_ids = list(payload.get("transaction_ids", []))
        except (KeyError, TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_exception_request",
                "message": "actor_id, biz_side and exception_code are required.",
            }

        try:
            case, record = self._reconciliation_service.record_exception(
                actor_id=actor_id,
                biz_side=biz_side,
                exception_code=exception_code,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                oa_ids=list(payload.get("oa_ids", [])),
                resolution_action=payload.get("resolution_action"),
                note=payload.get("note"),
            )
        except KeyError as exc:
            return HTTPStatus.NOT_FOUND, {"error": "reconciliation_object_not_found", "message": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_workbench_exception_request", "message": str(exc)}
        ledgers = self._ledger_service.sync_from_case(case, exception_record=record)
        return HTTPStatus.OK, {"case": case, "exception_record": record, "ledgers": ledgers}

    def offline(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            actor_id = str(payload["actor_id"])
            biz_side = str(payload["biz_side"])
            amount = payload["amount"]
            payment_method = str(payload["payment_method"])
            occurred_on = str(payload["occurred_on"])
            invoice_ids = list(payload.get("invoice_ids", []))
            transaction_ids = list(payload.get("transaction_ids", []))
        except (KeyError, TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_offline_request",
                "message": "actor_id, biz_side, amount, payment_method and occurred_on are required.",
            }

        try:
            case, record = self._reconciliation_service.record_offline_reconciliation(
                actor_id=actor_id,
                biz_side=biz_side,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                oa_ids=list(payload.get("oa_ids", [])),
                amount=amount,
                payment_method=payment_method,
                occurred_on=occurred_on,
                note=payload.get("note"),
            )
        except KeyError as exc:
            return HTTPStatus.NOT_FOUND, {"error": "reconciliation_object_not_found", "message": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_workbench_offline_request", "message": str(exc)}
        ledgers = self._ledger_service.sync_from_case(case)
        return HTTPStatus.OK, {"case": case, "offline_record": record, "ledgers": ledgers}

    def offset(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            actor_id = str(payload["actor_id"])
            receivable_invoice_ids = list(payload["receivable_invoice_ids"])
            payable_invoice_ids = list(payload["payable_invoice_ids"])
            reason = str(payload["reason"])
        except (KeyError, TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_workbench_offset_request",
                "message": "actor_id, receivable_invoice_ids, payable_invoice_ids and reason are required.",
            }

        try:
            case, offset_note = self._reconciliation_service.record_offset_reconciliation(
                actor_id=actor_id,
                receivable_invoice_ids=receivable_invoice_ids,
                payable_invoice_ids=payable_invoice_ids,
                reason=reason,
                note=payload.get("note"),
                amount=payload.get("amount"),
                oa_ids=list(payload.get("oa_ids", [])),
            )
        except KeyError as exc:
            return HTTPStatus.NOT_FOUND, {"error": "reconciliation_object_not_found", "message": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "invalid_workbench_offset_request", "message": str(exc)}
        return HTTPStatus.OK, {"case": case, "offset_note": offset_note}
