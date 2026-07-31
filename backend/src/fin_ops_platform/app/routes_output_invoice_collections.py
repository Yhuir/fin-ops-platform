from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.app.auth import OARequestSession, tenant_id_for_session
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionError,
)


ReadSessionResolver = Callable[
    [dict[str, str] | None], tuple[OARequestSession | None, Any | None]
]
JsonResponse = Callable[[HTTPStatus, object], Any]
XlsxResponse = Callable[[str, bytes], Any]
ErrorResponse = Callable[[OutputInvoiceCollectionError], Any]


class OutputInvoiceCollectionApiRoutes:
    """Read-only HTTP boundary for canonical output-invoice collection data."""

    def __init__(
        self,
        *,
        query_service: Any,
        resolve_read_session: ReadSessionResolver | None = None,
        json_response: JsonResponse | None = None,
        xlsx_response: XlsxResponse | None = None,
        error_response: ErrorResponse | None = None,
    ) -> None:
        self._query_service = query_service
        self._resolve_read_session = resolve_read_session
        self._json_response = json_response
        self._xlsx_response = xlsx_response
        self._error_response = error_response

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any | None:
        del body
        if method == "GET" and route_path == "/api/output-invoice-collections/rows":
            return self._json_read(
                headers, lambda session: self.rows(query, session=session)
            )
        if (
            method == "GET"
            and route_path == "/api/output-invoice-collections/filter-options"
        ):
            return self._json_read(
                headers, lambda session: self.filter_options(query, session=session)
            )
        if (
            method == "GET"
            and route_path == "/api/output-invoice-collections/export-preview"
        ):
            return self._json_read(
                headers, lambda session: self.export_preview(query, session=session)
            )
        if method == "GET" and route_path == "/api/output-invoice-collections/export":
            session, auth_error = self._read_session(headers)
            if auth_error is not None:
                return auth_error
            try:
                filename, content = self.export(query, session=session)
            except OutputInvoiceCollectionError as exc:
                return self._error(exc)
            return self._xlsx(filename, content)
        if (
            method == "GET"
            and route_path.startswith("/api/output-invoice-collections/invoices/")
            and route_path.endswith("/detail")
        ):
            invoice_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.invoice_detail(invoice_id, session=session),
                ),
            )
        if (
            method == "GET"
            and route_path.startswith(
                "/api/output-invoice-collections/bank-transactions/"
            )
            and route_path.endswith("/detail")
        ):
            bank_transaction_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.bank_transaction_detail(
                        bank_transaction_id, session=session
                    ),
                ),
            )
        if (
            method == "GET"
            and route_path.startswith("/api/output-invoice-collections/rows/")
            and route_path.endswith("/relation-details")
        ):
            row_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(
                headers,
                lambda session: (
                    HTTPStatus.OK,
                    self.relation_details(row_id, query, session=session),
                ),
            )
        return None

    def rows(
        self,
        query: dict[str, list[str]],
        *,
        session: OARequestSession | None = None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.OK, self._query_service.rows(
            query, tenant_id=_tenant_id(session)
        )

    def filter_options(
        self,
        query: dict[str, list[str]],
        *,
        session: OARequestSession | None = None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.OK, self._query_service.filter_options(
            query, tenant_id=_tenant_id(session)
        )

    def export_preview(
        self,
        query: dict[str, list[str]],
        *,
        session: OARequestSession | None = None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        return HTTPStatus.OK, self._query_service.export_preview(
            query, tenant_id=_tenant_id(session)
        )

    def export(
        self,
        query: dict[str, list[str]],
        *,
        session: OARequestSession | None = None,
    ) -> tuple[str, bytes]:
        return self._query_service.export(query, tenant_id=_tenant_id(session))

    def invoice_detail(
        self,
        invoice_id: str,
        *,
        session: OARequestSession | None = None,
    ) -> dict[str, Any]:
        return self._query_service.invoice_detail(
            invoice_id, tenant_id=_tenant_id(session)
        )

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
        *,
        session: OARequestSession | None = None,
    ) -> dict[str, Any]:
        return self._query_service.bank_transaction_detail(
            bank_transaction_id, tenant_id=_tenant_id(session)
        )

    def relation_details(
        self,
        row_id: str,
        query: dict[str, list[str]],
        *,
        session: OARequestSession | None = None,
    ) -> dict[str, Any]:
        return self._query_service.relation_details(
            row_id, query, tenant_id=_tenant_id(session)
        )

    def _json_read(
        self,
        headers: dict[str, str] | None,
        callback: Callable[
            [OARequestSession | None], tuple[HTTPStatus, dict[str, Any]]
        ],
    ) -> Any:
        session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            status_code, payload = callback(session)
        except OutputInvoiceCollectionError as exc:
            return self._error(exc)
        return self._json(status_code, payload)

    def _read_session(
        self, headers: dict[str, str] | None
    ) -> tuple[OARequestSession | None, Any | None]:
        if callable(self._resolve_read_session):
            return self._resolve_read_session(headers)
        return None, None

    def _json(self, status: HTTPStatus, payload: object) -> Any:
        if not callable(self._json_response):
            raise RuntimeError(
                "output invoice collection json response port is not configured"
            )
        return self._json_response(status, payload)

    def _xlsx(self, filename: str, content: bytes) -> Any:
        if not callable(self._xlsx_response):
            raise RuntimeError(
                "output invoice collection xlsx response port is not configured"
            )
        return self._xlsx_response(filename, content)

    def _error(self, exc: OutputInvoiceCollectionError) -> Any:
        if not callable(self._error_response):
            raise exc
        return self._error_response(exc)


def _tenant_id(session: OARequestSession | None) -> str:
    return tenant_id_for_session(session) if session is not None else "default"
