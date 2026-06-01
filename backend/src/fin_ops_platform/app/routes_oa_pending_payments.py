from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fin_ops_platform.services.oa_pending_payment_read_model_service import OaPendingPaymentReadModelService
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService


class OaPendingPaymentApiRoutes:
    def __init__(
        self,
        query_service: OaPendingPaymentQueryService,
        *,
        read_model_service: OaPendingPaymentReadModelService | None = None,
    ) -> None:
        self._query_service = query_service
        self._read_model_service = read_model_service

    def rows(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        if self._read_model_service is not None:
            payload = self._read_model_service.rows(query)
            return _read_model_status_code(payload), payload
        payload = self._query_service.list_rows(
            page=query.get("page", [1])[0],
            page_size=query.get("page_size", [50])[0],
            keyword=query.get("keyword", [None])[0],
            month=query.get("month", [None])[0],
            trade_date_from=query.get("trade_date_from", [None])[0],
            trade_date_to=query.get("trade_date_to", [None])[0],
            filters=query.get("filters", [None])[0],
            sort_field=query.get("sort_field", ["bank_trade_time"])[0],
            sort_direction=query.get("sort_direction", ["desc"])[0],
        )
        return HTTPStatus.OK, payload

    def filter_options(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        if self._read_model_service is not None:
            return self._read_model_service.filter_options(query)
        return HTTPStatus.OK, self._query_service.filter_options(
            keyword=query.get("keyword", [None])[0],
            month=query.get("month", [None])[0],
            trade_date_from=query.get("trade_date_from", [None])[0],
            trade_date_to=query.get("trade_date_to", [None])[0],
            filters=query.get("filters", [None])[0],
        )

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        if self._read_model_service is not None:
            return self._read_model_service.oa_detail(oa_id)
        return self._query_service.oa_detail(oa_id)

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        if self._read_model_service is not None:
            return self._read_model_service.bank_transaction_detail(bank_transaction_id)
        return self._query_service.bank_transaction_detail(bank_transaction_id)

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        if self._read_model_service is not None:
            return self._read_model_service.invoice_detail(invoice_id)
        return self._query_service.invoice_detail(invoice_id)

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        if self._read_model_service is not None:
            return self._read_model_service.relation_details(row_id, kind=query.get("kind", [""])[0])
        return self._query_service.row_relation_details(row_id, kind=query.get("kind", [""])[0])


def _read_model_status_code(payload: dict[str, Any]) -> HTTPStatus:
    return HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
