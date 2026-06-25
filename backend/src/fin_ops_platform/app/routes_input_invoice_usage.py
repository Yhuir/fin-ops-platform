from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    InputInvoiceUsageQueryService,
)
from fin_ops_platform.services.input_invoice_usage_export_service import (
    InputInvoiceUsageExportError,
    InputInvoiceUsageExportService,
)


class InputInvoiceUsageApiRoutes:
    def __init__(
        self,
        *,
        query_service: InputInvoiceUsageQueryService,
        rows_from_sql_read_model: Callable[[dict[str, list[str]]], dict[str, object] | None],
        all_rows_from_sql_read_model: Callable[[dict[str, list[str]]], dict[str, object] | Any | None],
        relation_details_from_sql_read_model: Callable[[str, dict[str, list[str]]], dict[str, object] | None],
        export_service: InputInvoiceUsageExportService,
        resolve_read_session: Callable[..., tuple[Any | None, Any | None]],
        export_query_kwargs: Callable[[dict[str, list[str]]], dict[str, object]],
        export_error_response: Callable[[InputInvoiceUsageExportError], Any],
        record_export_download: Callable[[Any | None, str, dict[str, list[str]]], None],
        xlsx_response: Callable[[str, bytes], Any],
        json_response: Callable[[HTTPStatus, object], Any],
        input_usage_error_response: Callable[[InputInvoiceUsageError], Any],
    ) -> None:
        self._query_service = query_service
        self._rows_from_sql_read_model = rows_from_sql_read_model
        self._all_rows_from_sql_read_model = all_rows_from_sql_read_model
        self._relation_details_from_sql_read_model = relation_details_from_sql_read_model
        self._export_service = export_service
        self._resolve_read_session = resolve_read_session
        self._export_query_kwargs = export_query_kwargs
        self._export_error_response = export_error_response
        self._record_export_download = record_export_download
        self._xlsx_response = xlsx_response
        self._json_response = json_response
        self._input_usage_error_response = input_usage_error_response

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        headers: dict[str, str] | None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/input-invoice-usage/rows":
            return self.rows(query)
        if method == "GET" and route_path == "/api/input-invoice-usage/filter-options":
            return self.filter_options(query)
        if method == "GET" and route_path == "/api/input-invoice-usage/export-preview":
            return self.export_preview(query, headers)
        if method == "GET" and route_path == "/api/input-invoice-usage/export":
            return self.export(query, headers)
        if method == "GET" and route_path == "/api/input-invoice-usage/payment-status-rules":
            return self.payment_status_rules()
        if method == "GET" and route_path.startswith("/api/input-invoice-usage/invoices/") and route_path.endswith("/detail"):
            invoice_id = unquote(route_path.rsplit("/", 2)[-2])
            return self.invoice_detail(invoice_id)
        if method == "GET" and route_path.startswith("/api/input-invoice-usage/bank-transactions/") and route_path.endswith("/detail"):
            bank_transaction_id = unquote(route_path.rsplit("/", 2)[-2])
            return self.bank_transaction_detail(bank_transaction_id)
        if method == "GET" and route_path.startswith("/api/input-invoice-usage/oa/") and route_path.endswith("/detail"):
            oa_id = unquote(route_path.rsplit("/", 2)[-2])
            return self.oa_detail(oa_id)
        if method == "GET" and route_path.startswith("/api/input-invoice-usage/rows/") and route_path.endswith("/relation-details"):
            row_id = unquote(route_path.rsplit("/", 2)[-2])
            return self.relation_details(row_id, query)
        return None

    def rows(self, query: dict[str, list[str]]) -> Any:
        try:
            sql_payload = self._rows_from_sql_read_model(query)
            if sql_payload is not None:
                status_code = HTTPStatus.ACCEPTED if sql_payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
                return self._json_response(status_code, sql_payload)
            payload = self._query_service.list_rows(
                page=query.get("page", [1])[0],
                page_size=query.get("page_size", [50])[0],
                keyword=query.get("keyword", [None])[0],
                invoice_date_from=query.get("invoice_date_from", [None])[0],
                invoice_date_to=query.get("invoice_date_to", [None])[0],
                month=query.get("month", [None])[0],
                filters=query.get("filters", [None])[0],
                sort_field=query.get("sort_field", ["invoice_date"])[0],
                sort_direction=query.get("sort_direction", ["desc"])[0],
            )
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def filter_options(self, query: dict[str, list[str]]) -> Any:
        try:
            sql_rows_payload = self._all_rows_from_sql_read_model(query)
            if _is_response(sql_rows_payload):
                return sql_rows_payload
            if isinstance(sql_rows_payload, dict):
                payload = self._query_service.filter_options_for_rows(
                    rows=list(sql_rows_payload.get("rows") or []),
                    keyword=query.get("keyword", [None])[0],
                    invoice_date_from=query.get("invoice_date_from", [None])[0],
                    invoice_date_to=query.get("invoice_date_to", [None])[0],
                    month=query.get("month", [None])[0],
                    filters=query.get("filters", [None])[0],
                )
                payload["read_model_status"] = "fresh"
                payload["read_model_scope_key"] = sql_rows_payload.get("read_model_scope_key")
            else:
                payload = self._query_service.filter_options(
                    keyword=query.get("keyword", [None])[0],
                    invoice_date_from=query.get("invoice_date_from", [None])[0],
                    invoice_date_to=query.get("invoice_date_to", [None])[0],
                    month=query.get("month", [None])[0],
                    filters=query.get("filters", [None])[0],
                )
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def invoice_detail(self, invoice_id: str) -> Any:
        try:
            payload = self._query_service.invoice_detail(invoice_id)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def bank_transaction_detail(self, bank_transaction_id: str) -> Any:
        try:
            payload = self._query_service.bank_transaction_detail(bank_transaction_id)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def oa_detail(self, oa_id: str) -> Any:
        try:
            payload = self._query_service.oa_detail(oa_id)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> Any:
        try:
            sql_payload = self._relation_details_from_sql_read_model(row_id, query)
            if sql_payload is not None:
                status_code = HTTPStatus.ACCEPTED if sql_payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
                return self._json_response(status_code, sql_payload)
            payload = self._query_service.row_relation_details(
                row_id,
                kind=query.get("kind", [""])[0],
            )
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def payment_status_rules(self) -> Any:
        return self._json_response(HTTPStatus.OK, self._query_service.payment_status_rules())

    def export_preview(self, query: dict[str, list[str]], headers: dict[str, str] | None) -> Any:
        _session, auth_error = self._resolve_read_session(
            headers,
            denied_message="当前账户没有访问进项发票使用情况页面权限。",
        )
        if auth_error is not None:
            return auth_error
        try:
            payload = self._export_service.export_preview(
                **self._export_query_kwargs(query)
            )
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        except InputInvoiceUsageExportError as exc:
            return self._export_error_response(exc)
        status = HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
        return self._json_response(status, payload)

    def export(self, query: dict[str, list[str]], headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read_session(
            headers,
            denied_message="当前账户没有访问进项发票使用情况页面权限。",
        )
        if auth_error is not None:
            return auth_error
        try:
            filename, content = self._export_service.export(
                **self._export_query_kwargs(query)
            )
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        except InputInvoiceUsageExportError as exc:
            return self._export_error_response(exc)
        self._record_export_download(session, filename, query)
        return self._xlsx_response(filename, content)


def _is_response(value: object) -> bool:
    return hasattr(value, "status_code") and hasattr(value, "body") and hasattr(value, "headers")
