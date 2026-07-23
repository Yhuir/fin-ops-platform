from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageError
from fin_ops_platform.services.input_invoice_usage_export_service import (
    InputInvoiceUsageExportError,
    InputInvoiceUsageExportService,
)
from fin_ops_platform.services.input_invoice_usage_read_model_detail_service import (
    InputInvoiceUsageReadModelDetailService,
)
from fin_ops_platform.services.input_invoice_usage_read_model_fresh_gate_service import (
    InputInvoiceUsageReadModelFreshGateService,
)


class InputInvoiceUsageApiRoutes:
    def __init__(
        self,
        *,
        invoice_detail_loader: Callable[[str], dict[str, Any]],
        bank_transaction_detail_loader: Callable[[str], dict[str, Any]],
        oa_detail_loader: Callable[[str], dict[str, Any]],
        payment_status_rules_loader: Callable[[], dict[str, Any]],
        rows_from_sql_read_model: Callable[[dict[str, list[str]]], dict[str, object] | None],
        filter_options_from_sql_read_model: Callable[[dict[str, list[str]]], dict[str, object] | Any | None],
        relation_details_from_sql_read_model: Callable[[str, dict[str, list[str]]], dict[str, object] | None],
        export_service: InputInvoiceUsageExportService,
        resolve_read_session: Callable[..., tuple[Any | None, Any | None]],
        export_query_kwargs: Callable[[dict[str, list[str]]], dict[str, object]],
        export_error_response: Callable[[InputInvoiceUsageExportError], Any],
        record_export_download: Callable[[Any | None, str, dict[str, list[str]]], None],
        xlsx_response: Callable[[str, bytes], Any],
        app_settings_service: Any,
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        payment_rules_error_response: Callable[[AppSettingsValidationError], Any],
        json_response: Callable[[HTTPStatus, object], Any],
        input_usage_error_response: Callable[[InputInvoiceUsageError], Any],
        dependency_identity: object | None = None,
    ) -> None:
        self._invoice_detail_loader = invoice_detail_loader
        self._bank_transaction_detail_loader = bank_transaction_detail_loader
        self._oa_detail_loader = oa_detail_loader
        self._payment_status_rules_loader = payment_status_rules_loader
        self._rows_from_sql_read_model = rows_from_sql_read_model
        self._filter_options_from_sql_read_model = filter_options_from_sql_read_model
        self._relation_details_from_sql_read_model = relation_details_from_sql_read_model
        self._export_service = export_service
        self._resolve_read_session = resolve_read_session
        self._export_query_kwargs = export_query_kwargs
        self._export_error_response = export_error_response
        self._record_export_download = record_export_download
        self._xlsx_response = xlsx_response
        self._app_settings_service = app_settings_service
        self._load_json_body = load_json_body
        self._payment_rules_error_response = payment_rules_error_response
        self._json_response = json_response
        self._input_usage_error_response = input_usage_error_response
        self._dependency_identity = dependency_identity

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
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
        if method == "PUT" and route_path == "/api/input-invoice-usage/payment-status-rules":
            return self.update_payment_status_rules(body, headers)
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
            payload = InputInvoiceUsageReadModelFreshGateService.refreshing_payload(
                scope_key=InputInvoiceUsageReadModelFreshGateService.scope_key_from_query(query),
            )
            return self._json_response(HTTPStatus.ACCEPTED, payload)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)

    def filter_options(self, query: dict[str, list[str]]) -> Any:
        try:
            payload = self._filter_options_from_sql_read_model(query)
            if _is_response(payload):
                return payload
            if isinstance(payload, dict):
                if payload.get("read_model_status") == "refreshing":
                    return self._json_response(HTTPStatus.ACCEPTED, payload)
                return self._json_response(HTTPStatus.OK, payload)
            else:
                payload = InputInvoiceUsageReadModelFreshGateService.refreshing_payload(
                    scope_key=InputInvoiceUsageReadModelFreshGateService.scope_key_from_query(query),
                )
                return self._json_response(HTTPStatus.ACCEPTED, payload)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)

    def invoice_detail(self, invoice_id: str) -> Any:
        try:
            payload = self._invoice_detail_loader(invoice_id)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def bank_transaction_detail(self, bank_transaction_id: str) -> Any:
        try:
            payload = self._bank_transaction_detail_loader(bank_transaction_id)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def oa_detail(self, oa_id: str) -> Any:
        try:
            payload = self._oa_detail_loader(oa_id)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> Any:
        try:
            sql_payload = self._relation_details_from_sql_read_model(row_id, query)
            if sql_payload is not None:
                status_code = HTTPStatus.ACCEPTED if sql_payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
                return self._json_response(status_code, sql_payload)
            payload = InputInvoiceUsageReadModelDetailService.refreshing_payload(
                kind=query.get("kind", [""])[0],
                scope_key=InputInvoiceUsageReadModelFreshGateService.scope_key_from_query(
                    query
                ),
            )
            return self._json_response(HTTPStatus.ACCEPTED, payload)
        except InputInvoiceUsageError as exc:
            return self._input_usage_error_response(exc)
        return self._json_response(HTTPStatus.OK, payload)

    def payment_status_rules(self) -> Any:
        return self._json_response(HTTPStatus.OK, self._payment_status_rules_loader())

    def update_payment_status_rules(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, auth_error = self._resolve_read_session(
            headers,
            denied_message="当前账户没有访问进项发票使用情况页面权限。",
        )
        if auth_error is not None:
            return auth_error
        if session is not None and not session.can_mutate_data:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": "当前账户没有保存进项发票支付状态规则权限。"},
            )
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = (
            session.identity.username or session.identity.user_id
            if session is not None
            else "input_invoice_usage_payment_rules"
        )
        try:
            updated = self._app_settings_service.update_input_invoice_usage_payment_status_rules(
                payload,
                actor_id=str(actor_id or "input_invoice_usage_payment_rules"),
            )
        except AppSettingsValidationError as exc:
            return self._payment_rules_error_response(exc)
        return self._json_response(HTTPStatus.OK, updated)

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
