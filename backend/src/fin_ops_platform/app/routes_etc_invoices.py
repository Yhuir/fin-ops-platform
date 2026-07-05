from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.etc_service import EtcInvoiceRequestError


class EtcInvoiceApiRoutes:
    def __init__(
        self,
        *,
        etc_service: Any,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        serialize_invoice: Callable[[object], dict[str, object]],
    ) -> None:
        self._etc_service = etc_service
        self._json_response = json_response
        self._serialize_invoice = serialize_invoice

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        _body: str | bytes | None,
    ) -> Any:
        if method == "GET" and route_path == "/api/etc/invoices":
            return self.list_invoices(
                status=query.get("status", [None])[0],
                month=query.get("month", [None])[0],
                plate=query.get("plate", [None])[0],
                keyword=query.get("keyword", [None])[0],
                import_batch_id=query.get("importBatchId", query.get("import_batch_id", [None]))[0],
                page=query.get("page", [None])[0],
                page_size=query.get("page_size", [None])[0],
            )
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_invoice_route"})

    def list_invoices(
        self,
        *,
        status: str | None,
        month: str | None,
        plate: str | None,
        keyword: str | None,
        import_batch_id: str | None,
        page: str | None,
        page_size: str | None,
    ) -> Any:
        try:
            resolved_page = int(page) if page not in (None, "") else 1
            resolved_page_size = int(page_size) if page_size not in (None, "") else 50
            invoices, total, counts = self._etc_service.list_invoices(
                status=status or None,
                month=month or None,
                plate=plate or None,
                keyword=keyword or None,
                import_batch_id=import_batch_id or None,
                page=resolved_page,
                page_size=resolved_page_size,
            )
        except (ValueError, EtcInvoiceRequestError) as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_invoice_request", "message": str(error)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "items": [self._serialize_invoice(invoice) for invoice in invoices],
                "counts": counts,
                "page": max(resolved_page, 1),
                "pageSize": min(max(resolved_page_size, 1), 500),
                "total": total,
            },
        )
