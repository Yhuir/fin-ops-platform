from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.oa_pending_payment_read_model_service import OaPendingPaymentReadModelService
from fin_ops_platform.services.oa_pending_payment_command_service import OaPendingPaymentCommandService
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentError, OaPendingPaymentQueryService


ReadSessionResolver = Callable[[dict[str, str] | None], tuple[Any | None, Any | None]]
WriteAuthContext = Callable[[dict[str, str] | None], tuple[str, str] | Any]
JsonResponse = Callable[[HTTPStatus, object], Any]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
ErrorResponse = Callable[[OaPendingPaymentError], Any]


class OaPendingPaymentApiRoutes:
    def __init__(
        self,
        query_service: OaPendingPaymentQueryService,
        *,
        read_model_service: OaPendingPaymentReadModelService | None = None,
        command_service: OaPendingPaymentCommandService | None = None,
        resolve_read_session: ReadSessionResolver | None = None,
        write_auth_context: WriteAuthContext | None = None,
        json_response: JsonResponse | None = None,
        load_json_body: JsonBodyLoader | None = None,
        error_response: ErrorResponse | None = None,
    ) -> None:
        self._query_service = query_service
        self._read_model_service = read_model_service
        self._command_service = command_service
        self._resolve_read_session = resolve_read_session
        self._write_auth_context = write_auth_context
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._error_response = error_response

    def configure_platform_ports(
        self,
        *,
        resolve_read_session: ReadSessionResolver,
        write_auth_context: WriteAuthContext,
        json_response: JsonResponse,
        load_json_body: JsonBodyLoader,
        error_response: ErrorResponse,
    ) -> "OaPendingPaymentApiRoutes":
        self._resolve_read_session = resolve_read_session
        self._write_auth_context = write_auth_context
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._error_response = error_response
        return self

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/oa-pending-payments/rows":
            return self._json_read(headers, lambda: self.rows(query))
        if method == "GET" and route_path == "/api/oa-pending-payments/filter-options":
            return self._json_read(headers, lambda: self.filter_options(query))
        if method == "GET" and route_path == "/api/oa-pending-payments/bank-transaction-candidates":
            return self._json_read(headers, lambda: (HTTPStatus.OK, self.bank_transaction_candidates(query)))
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/oa/") and route_path.endswith("/detail"):
            oa_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: self._detail_response(self.oa_detail(oa_id)))
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/bank-transactions/") and route_path.endswith("/detail"):
            bank_transaction_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: self._detail_response(self.bank_transaction_detail(bank_transaction_id)))
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/invoices/") and route_path.endswith("/detail"):
            invoice_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: self._detail_response(self.invoice_detail(invoice_id)))
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/rows/") and route_path.endswith("/relation-details"):
            row_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: self._detail_response(self.relation_details(row_id, query)))
        if method == "POST" and route_path == "/api/oa-pending-payments/writeback-paid":
            return self._json_write(body, headers, lambda payload, actor_id: self.writeback_paid(payload, actor_id=actor_id))
        if method == "POST" and route_path == "/api/oa-pending-payments/link-bank-transactions":
            return self._json_write(body, headers, lambda payload, actor_id: self.link_bank_transactions(payload, actor_id=actor_id))
        return None

    def rows(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        payload = self._read_model_service_required().rows(query)
        return _read_model_status_code(payload), payload

    def filter_options(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        return self._read_model_service_required().filter_options(query)

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        return self._read_model_service_required().oa_detail(oa_id)

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        return self._read_model_service_required().bank_transaction_detail(bank_transaction_id)

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        return self._read_model_service_required().invoice_detail(invoice_id)

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._read_model_service_required().relation_details(row_id, kind=query.get("kind", [""])[0])

    def link_bank_transactions(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if self._command_service is None:
            raise RuntimeError("OA pending payment command service is not configured.")
        return self._command_service.link_bank_transactions(payload, actor_id=actor_id)

    def writeback_paid(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if self._command_service is None:
            raise RuntimeError("OA pending payment command service is not configured.")
        return self._command_service.writeback_paid(payload, actor_id=actor_id)

    def bank_transaction_candidates(self, query: dict[str, list[str]]) -> dict[str, Any]:
        if self._command_service is None:
            raise RuntimeError("OA pending payment command service is not configured.")
        return self._command_service.bank_transaction_candidates(query)

    def _json_read(self, headers: dict[str, str] | None, action: Callable[[], tuple[HTTPStatus, dict[str, Any]]]) -> Any:
        _session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            status_code, payload = action()
        except OaPendingPaymentError as exc:
            return self._error(exc)
        except RuntimeError as exc:
            return self._command_unavailable(exc)
        return self._json(status_code, payload)

    def _json_write(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        action: Callable[[dict[str, Any], str], dict[str, Any]],
    ) -> Any:
        if not callable(self._load_json_body):
            raise RuntimeError("OA pending payment body loader is not configured.")
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        auth_context = self._write_auth(headers)
        if not isinstance(auth_context, tuple):
            return auth_context
        actor_id, _tenant_id = auth_context
        try:
            result = action(payload, actor_id)
        except OaPendingPaymentError as exc:
            return self._error(exc)
        except RuntimeError as exc:
            return self._command_unavailable(exc)
        return self._json(HTTPStatus.OK, result)

    def _read_session(self, headers: dict[str, str] | None) -> tuple[Any | None, Any | None]:
        if not callable(self._resolve_read_session):
            return None, None
        return self._resolve_read_session(headers)

    def _write_auth(self, headers: dict[str, str] | None) -> tuple[str, str] | Any:
        if not callable(self._write_auth_context):
            raise RuntimeError("OA pending payment write auth is not configured.")
        return self._write_auth_context(headers)

    def _detail_response(self, payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        return _read_model_status_code(payload), payload

    def _read_model_service_required(self) -> OaPendingPaymentReadModelService:
        if self._read_model_service is None:
            raise RuntimeError("OA pending payment read model service is not configured.")
        return self._read_model_service

    def _json(self, status_code: HTTPStatus, payload: object) -> Any:
        if not callable(self._json_response):
            return status_code, payload
        return self._json_response(status_code, payload)

    def _error(self, exc: OaPendingPaymentError) -> Any:
        if callable(self._error_response):
            return self._error_response(exc)
        raise exc

    def _command_unavailable(self, exc: RuntimeError) -> Any:
        return self._json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": {
                    "code": "oa_pending_payment_command_unavailable",
                    "message": str(exc),
                    "details": {},
                }
            },
        )


def _read_model_status_code(payload: dict[str, Any]) -> HTTPStatus:
    return HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
