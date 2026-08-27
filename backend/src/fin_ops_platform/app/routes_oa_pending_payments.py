from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.oa_pending_payment_command_service import OaPendingPaymentCommandService
from fin_ops_platform.services.oa_pending_payment_query_contract import OaPendingPaymentError
from fin_ops_platform.services.oa_pending_payment_query_service import OaPendingPaymentQueryService


ReadSessionResolver = Callable[[dict[str, str] | None], tuple[Any | None, Any | None]]
ReadTenantResolver = Callable[[Any], str]
WriteAuthContext = Callable[[dict[str, str] | None], tuple[str, str] | Any]
JsonResponse = Callable[..., Any]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
ErrorResponse = Callable[[OaPendingPaymentError], Any]
XlsxResponse = Callable[[str, bytes], Any]
ExportAuditRecorder = Callable[[Any | None, str, list[str], dict[str, int]], None]


class OaPendingPaymentApiRoutes:
    def __init__(
        self,
        *,
        query_service: OaPendingPaymentQueryService | None = None,
        command_service: OaPendingPaymentCommandService | None = None,
        resolve_read_session: ReadSessionResolver | None = None,
        resolve_read_tenant: ReadTenantResolver | None = None,
        write_auth_context: WriteAuthContext | None = None,
        json_response: JsonResponse | None = None,
        load_json_body: JsonBodyLoader | None = None,
        error_response: ErrorResponse | None = None,
        xlsx_response: XlsxResponse | None = None,
        record_export_download: ExportAuditRecorder | None = None,
    ) -> None:
        self._query_service = query_service
        self._command_service = command_service
        self._resolve_read_session = resolve_read_session
        self._resolve_read_tenant = resolve_read_tenant
        self._write_auth_context = write_auth_context
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._error_response = error_response
        self._xlsx_response = xlsx_response
        self._record_export_download = record_export_download

    def configure_platform_ports(
        self,
        *,
        resolve_read_session: ReadSessionResolver,
        resolve_read_tenant: ReadTenantResolver,
        write_auth_context: WriteAuthContext,
        json_response: JsonResponse,
        load_json_body: JsonBodyLoader,
        error_response: ErrorResponse,
        xlsx_response: XlsxResponse | None = None,
        record_export_download: ExportAuditRecorder | None = None,
    ) -> "OaPendingPaymentApiRoutes":
        self._resolve_read_session = resolve_read_session
        self._resolve_read_tenant = resolve_read_tenant
        self._write_auth_context = write_auth_context
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._error_response = error_response
        self._xlsx_response = xlsx_response
        self._record_export_download = record_export_download
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
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.rows(query, tenant_id=self._tenant_id(session)),
                ),
            )
        if method == "GET" and route_path == "/api/oa-pending-payments/export":
            return self._xlsx_read(headers, query)
        if method == "GET" and route_path == "/api/oa-pending-payments/bank-transaction-candidates":
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.bank_transaction_candidates(query, tenant_id=self._tenant_id(session)),
                ),
            )
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/oa/") and route_path.endswith("/detail"):
            oa_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.oa_detail(oa_id, query, tenant_id=self._tenant_id(session)),
                ),
            )
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/bank-transactions/") and route_path.endswith("/detail"):
            bank_transaction_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.bank_transaction_detail(
                        bank_transaction_id,
                        query,
                        tenant_id=self._tenant_id(session),
                    ),
                ),
            )
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/invoices/") and route_path.endswith("/detail"):
            invoice_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.invoice_detail(invoice_id, query, tenant_id=self._tenant_id(session)),
                ),
            )
        if method == "GET" and route_path.startswith("/api/oa-pending-payments/rows/") and route_path.endswith("/relation-details"):
            row_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.relation_details(row_id, query, tenant_id=self._tenant_id(session)),
                ),
            )
        if method == "POST" and route_path == "/api/oa-pending-payments/link-bank-transactions":
            return self._json_write(body, headers, lambda payload, actor_id: self.link_bank_transactions(payload, actor_id=actor_id))
        return None

    def rows(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._query_service_required().rows(query, tenant_id=tenant_id)

    def export_sources(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._query_service_required().export_sources(query, tenant_id=tenant_id)

    def oa_detail(
        self,
        oa_id: str,
        query: dict[str, list[str]] | None = None,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._query_service_required().oa_detail(
            oa_id,
            tenant_id=tenant_id,
            requested_scope_key=_scope_key_from_query(query),
        )

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
        query: dict[str, list[str]] | None = None,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._query_service_required().bank_transaction_detail(
            bank_transaction_id,
            tenant_id=tenant_id,
            requested_scope_key=_scope_key_from_query(query),
        )

    def invoice_detail(
        self,
        invoice_id: str,
        query: dict[str, list[str]] | None = None,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._query_service_required().invoice_detail(
            invoice_id,
            tenant_id=tenant_id,
            requested_scope_key=_scope_key_from_query(query),
        )

    def relation_details(
        self,
        row_id: str,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._query_service_required().relation_details(
            row_id,
            kind=query.get("kind", [""])[0],
            tenant_id=tenant_id,
            requested_scope_key=_scope_key_from_query(query),
        )

    def link_bank_transactions(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if self._command_service is None:
            raise RuntimeError("OA pending payment command service is not configured.")
        return self._command_service.link_bank_transactions(payload, actor_id=actor_id)

    def bank_transaction_candidates(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._query_service_required().bank_transaction_candidates(
            query,
            tenant_id=tenant_id,
        )

    def _json_read(self, headers: dict[str, str] | None, action: Callable[[Any], tuple[Any, ...]]) -> Any:
        session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            result = action(session)
            status_code, payload = result[:2]
            response_headers = result[2] if len(result) > 2 and isinstance(result[2], dict) else None
        except OaPendingPaymentError as exc:
            return self._error(exc)
        except RuntimeError as exc:
            return self._service_unavailable(exc)
        return self._json(status_code, payload, response_headers=response_headers)

    def _xlsx_read(
        self,
        headers: dict[str, str] | None,
        query: dict[str, list[str]],
    ) -> Any:
        session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            result = self.export_sources(query, tenant_id=self._tenant_id(session))
            filename = str(result["filename"])
            sources = [str(source) for source in list(result.get("sources") or [])]
            counts = {
                str(source): int(count)
                for source, count in dict(result.get("counts") or {}).items()
            }
            if callable(self._record_export_download):
                self._record_export_download(session, filename, sources, counts)
        except OaPendingPaymentError as exc:
            return self._error(exc)
        except RuntimeError as exc:
            return self._service_unavailable(exc)
        if callable(self._xlsx_response):
            return self._xlsx_response(filename, bytes(result["content"]))
        return HTTPStatus.OK, bytes(result["content"]), {"Content-Disposition": filename}

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

    def _tenant_id(self, session: Any) -> str:
        if not callable(self._resolve_read_tenant):
            return "default"
        return str(self._resolve_read_tenant(session) or "default").strip() or "default"

    def _write_auth(self, headers: dict[str, str] | None) -> tuple[str, str] | Any:
        if not callable(self._write_auth_context):
            raise RuntimeError("OA pending payment write auth is not configured.")
        return self._write_auth_context(headers)

    def _query_service_required(self) -> OaPendingPaymentQueryService:
        if self._query_service is None:
            raise RuntimeError("OA pending payment canonical query service is not configured.")
        return self._query_service

    def _json(
        self,
        status_code: HTTPStatus,
        payload: object,
        *,
        response_headers: dict[str, str] | None = None,
    ) -> Any:
        if not callable(self._json_response):
            return (status_code, payload, response_headers) if response_headers else (status_code, payload)
        if response_headers:
            return self._json_response(status_code, payload, response_headers)
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

    def _service_unavailable(self, exc: RuntimeError) -> Any:
        return self._json(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": {
                    "code": "oa_pending_payment_service_unavailable",
                    "message": str(exc),
                    "details": {},
                }
            },
        )

def _scope_key_from_query(
    query: dict[str, list[str]] | None,
) -> str | None:
    month = str((query or {}).get("month", [""])[0] or "").strip()
    return month[:7] if len(month) >= 7 and month[4] == "-" else None
