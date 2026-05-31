from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService


SqlRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | Any | None]
SqlAllRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | Any | None]


class OaPendingPaymentApiRoutes:
    def __init__(
        self,
        query_service: OaPendingPaymentQueryService,
        *,
        sql_rows_provider: SqlRowsProvider | None = None,
        sql_all_rows_provider: SqlAllRowsProvider | None = None,
    ) -> None:
        self._query_service = query_service
        self._sql_rows_provider = sql_rows_provider
        self._sql_all_rows_provider = sql_all_rows_provider

    def rows(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        sql_payload = self._sql_rows_provider(query) if callable(self._sql_rows_provider) else None
        if isinstance(sql_payload, dict):
            status_code = HTTPStatus.ACCEPTED if sql_payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
            return status_code, sql_payload
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
        sql_rows_payload = self._sql_all_rows_provider(query) if callable(self._sql_all_rows_provider) else None
        if _is_response_like(sql_rows_payload):
            return HTTPStatus.ACCEPTED, _response_like_payload(sql_rows_payload)
        if isinstance(sql_rows_payload, dict):
            payload = self._query_service.filter_options_for_rows(
                rows=list(sql_rows_payload.get("rows") or []),
                keyword=query.get("keyword", [None])[0],
                month=query.get("month", [None])[0],
                trade_date_from=query.get("trade_date_from", [None])[0],
                trade_date_to=query.get("trade_date_to", [None])[0],
                filters=query.get("filters", [None])[0],
            )
            payload["read_model_status"] = "fresh"
            payload["readModelStatus"] = "fresh"
            payload["read_model_scope_key"] = sql_rows_payload.get("read_model_scope_key")
            return HTTPStatus.OK, payload
        return HTTPStatus.OK, self._query_service.filter_options(
            keyword=query.get("keyword", [None])[0],
            month=query.get("month", [None])[0],
            trade_date_from=query.get("trade_date_from", [None])[0],
            trade_date_to=query.get("trade_date_to", [None])[0],
            filters=query.get("filters", [None])[0],
        )

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        return self._query_service.oa_detail(oa_id)

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        return self._query_service.bank_transaction_detail(bank_transaction_id)

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        return self._query_service.invoice_detail(invoice_id)

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._query_service.row_relation_details(row_id, kind=query.get("kind", [""])[0])


def _is_response_like(value: Any) -> bool:
    return hasattr(value, "status_code") and hasattr(value, "body")


def _response_like_payload(value: Any) -> dict[str, Any]:
    import json

    try:
        return json.loads(value.body)
    except Exception:
        return {"read_model_status": "refreshing"}
