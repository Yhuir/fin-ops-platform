from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.pending_invoice_read_model_service import PendingInvoiceReadModelService
from fin_ops_platform.services.pending_invoice_rules_application_service import PendingInvoiceRulesApplicationService
from fin_ops_platform.services.pending_invoice_service import (
    PendingInvoiceApplicationService,
    PendingInvoiceError,
    PendingInvoiceQueryService,
)


@dataclass(frozen=True)
class PendingInvoiceExportFile:
    filename: str
    content: bytes
    content_type: str


class PendingInvoiceApiRoutes:
    def __init__(
        self,
        *,
        query_service: PendingInvoiceQueryService,
        application_service: PendingInvoiceApplicationService,
        read_model_service: PendingInvoiceReadModelService,
        rules_service: PendingInvoiceRulesApplicationService,
        export_content_type: str,
    ) -> None:
        self._query_service = query_service
        self._application_service = application_service
        self._read_model_service = read_model_service
        self._rules_service = rules_service
        self._export_content_type = export_content_type

    def rows(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        payload = self._read_model_service.rows(query)
        return _read_model_status_code(payload), payload

    def filter_options(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        rows_payload = self._read_model_service.all_rows(query)
        if rows_payload.get("read_model_status") != "fresh":
            return HTTPStatus.ACCEPTED, rows_payload
        payload = self._query_service.filter_options_for_rows(
            rows=list(rows_payload.get("rows") or []),
            direction=str(rows_payload.get("direction") or query.get("direction", ["expense"])[0]),
            filter=str(rows_payload.get("filter") or query.get("filter", ["all"])[0]),
        )
        payload["read_model_status"] = "fresh"
        payload["read_model_scope_key"] = rows_payload.get("read_model_scope_key")
        return HTTPStatus.OK, payload

    def invoice_candidates(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._query_service.invoice_candidates(
            transaction_id=query.get("transaction_id", [""])[0],
            keyword=query.get("keyword", [None])[0],
            seller_name=query.get("seller_name", [None])[0],
            issue_date_from=query.get("issue_date_from", [None])[0],
            issue_date_to=query.get("issue_date_to", [None])[0],
            amount_min=query.get("amount_min", [None])[0],
            amount_max=query.get("amount_max", [None])[0],
            sort_field=query.get("sort_field", [None])[0],
            sort_direction=query.get("sort_direction", [None])[0],
            page=query.get("page", [1])[0],
            page_size=query.get("page_size", [50])[0],
        )

    def relation_detail(self, transaction_id: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        request_query = query or {}
        return self._query_service.relation_detail(
            transaction_id=transaction_id,
            direction=request_query.get("direction", ["expense"])[0],
        )

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        return self._query_service.bank_transaction_detail(bank_transaction_id)

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        return self._query_service.invoice_detail(invoice_id)

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        return self._query_service.oa_detail(oa_id)

    def attach_existing_preview(self, transaction_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._application_service.preview_attach_existing_invoice(
            transaction_id=transaction_id,
            payload=payload,
        )

    def attach_existing_confirm(
        self,
        transaction_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有选择已有发票权限。")
        return self._application_service.confirm_attach_existing_invoice(
            transaction_id=transaction_id,
            payload=payload,
            actor_id=_actor_id(session, "pending_invoice"),
        )

    def rules(self, query: dict[str, list[str]], *, session: OARequestSession | None) -> dict[str, Any]:
        return self._rules_service.get_rules(
            direction=query.get("direction", ["expense"])[0],
            can_save=bool(getattr(session, "can_mutate_data", True)),
        )

    def update_rules(
        self,
        query: dict[str, list[str]],
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        self._require_mutation(session, "当前账户没有保存待找发票规则权限。")
        try:
            return HTTPStatus.OK, self._rules_service.update_rules(
                direction=query.get("direction", ["expense"])[0],
                payload=payload,
                actor_id=_actor_id(session, "pending_invoice_rules"),
            )
        except AppSettingsValidationError as exc:
            status = HTTPStatus.CONFLICT if str(exc.error_code).endswith("_version_conflict") else HTTPStatus.BAD_REQUEST
            return status, {"error": exc.error_code, "message": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_pending_invoice_rules_request",
                "message": str(exc),
            }

    def update_income_status(
        self,
        transaction_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有标记收入流水开票状态权限。")
        return self._application_service.confirm_income_status_override(
            transaction_id=transaction_id,
            payload=payload,
            actor_id=_actor_id(session, "pending_invoice_income_status"),
        )

    def export_preview(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        rows_payload = self._read_model_service.all_rows(query)
        if rows_payload.get("read_model_status") != "fresh":
            return HTTPStatus.ACCEPTED, rows_payload
        return HTTPStatus.OK, self._query_service.export_preview_for_rows(
            rows=list(rows_payload.get("rows") or []),
            filters=_query_kwargs(query),
        )

    def export(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any] | PendingInvoiceExportFile]:
        rows_payload = self._read_model_service.all_rows(query)
        if rows_payload.get("read_model_status") != "fresh":
            return HTTPStatus.ACCEPTED, rows_payload
        filename, content = self._query_service.export_for_rows(rows=list(rows_payload.get("rows") or []))
        return HTTPStatus.OK, PendingInvoiceExportFile(
            filename=filename,
            content=content,
            content_type=self._export_content_type,
        )

    def manual_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._application_service.preview_manual_invoice(payload)

    def manual_confirm(self, payload: dict[str, Any], *, session: OARequestSession | None) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有手工补票权限。")
        return self._application_service.confirm_manual_invoice(
            payload,
            actor_id=_actor_id(session, "pending_invoice"),
        )

    @staticmethod
    def _require_mutation(session: OARequestSession | None, message: str) -> None:
        if not bool(getattr(session, "can_mutate_data", True)):
            raise PendingInvoiceError("permission_denied", message, status_code=HTTPStatus.FORBIDDEN)


def _read_model_status_code(payload: dict[str, Any]) -> HTTPStatus:
    return (
        HTTPStatus.ACCEPTED
        if payload.get("read_model_status") == "refreshing" and not payload.get("rows")
        else HTTPStatus.OK
    )


def _query_kwargs(query: dict[str, list[str]]) -> dict[str, object]:
    return {
        "direction": query.get("direction", ["expense"])[0],
        "filter": query.get("filter", ["all"])[0],
        "date_from": query.get("date_from", [None])[0],
        "date_to": query.get("date_to", [None])[0],
        "keyword": query.get("keyword", [None])[0],
        "filters": query.get("filters", [None])[0],
        "sort_field": query.get("sort_field", [None])[0],
        "sort_direction": query.get("sort_direction", [None])[0],
    }


def _actor_id(session: OARequestSession | None, fallback: str) -> str:
    identity = getattr(session, "identity", None)
    return str(getattr(identity, "username", "") or fallback).strip() or fallback
