from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.etc_service import (
    EtcBatchDeleteError,
    EtcBatchNotFoundError,
    EtcDraftRequestError,
    EtcInvoiceNotFoundError,
    EtcOAClientError,
)


class EtcLegacyBatchApiRoutes:
    def __init__(
        self,
        *,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        reconciliation_error_response: Callable[[ValueError], Any],
        read_facade: Any,
        delete_service: Any,
        lifecycle_service: Any,
        build_oa_client: Callable[[dict[str, str] | None], Any],
        legacy_business_delete: Callable[[str], Any | None],
        refresh_after_etc_invoice_link: Callable[[list[str], str], None],
        persist_state: Callable[[], None],
    ) -> None:
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._reconciliation_error_response = reconciliation_error_response
        self._read_facade = read_facade
        self._delete_service = delete_service
        self._lifecycle_service = lifecycle_service
        self._build_oa_client = build_oa_client
        self._legacy_business_delete = legacy_business_delete
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link
        self._persist_state = persist_state

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        if method == "GET" and route_path == "/api/etc/batches":
            return self._list_batches_response(
                status=query.get("status", [None])[0],
                month=query.get("month", [None])[0],
                plate=query.get("plate", [None])[0],
                keyword=query.get("keyword", [None])[0],
                page=query.get("page", [None])[0],
                page_size=query.get("page_size", query.get("pageSize", [None]))[0],
            )
        if method == "POST" and route_path == "/api/etc/batches/draft":
            return self._create_draft_response(body, headers)
        if route_path.startswith("/api/etc/batches/"):
            return self._route_batch(method, route_path, body, headers)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_batch_route"})

    def _route_batch(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        relative = route_path.removeprefix("/api/etc/batches/").strip("/")
        parts = [unquote(part) for part in relative.split("/") if part]
        if not parts:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_batch_route"})
        batch_id = parts[0]
        if method == "DELETE" and len(parts) == 1:
            return self._delete_response(batch_id)
        if method == "GET" and len(parts) == 1:
            return self._detail_response(batch_id)
        if method == "POST" and len(parts) == 2 and parts[1] == "draft":
            return self._create_draft_for_batch_response(batch_id, headers)
        if method == "POST" and len(parts) == 2 and parts[1] == "confirm-submitted":
            return self._confirm_submitted_response(batch_id)
        if method == "POST" and len(parts) == 2 and parts[1] == "mark-not-submitted":
            return self._mark_not_submitted_response(batch_id)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_batch_route"})

    def _list_batches_response(
        self,
        *,
        status: str | None,
        month: str | None,
        plate: str | None,
        keyword: str | None,
        page: str | None,
        page_size: str | None,
    ) -> Any:
        try:
            resolved_page = int(page) if page not in (None, "") else 1
            resolved_page_size = int(page_size) if page_size not in (None, "") else 50
        except ValueError:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_batch_request", "message": "page and page_size must be integers."},
            )
        payload = self._read_facade.list_payload(
            status=str(status or "").strip().lower(),
            month=month,
            plate=plate,
            keyword=keyword,
            page=resolved_page,
            page_size=resolved_page_size,
        )
        return self._json_response(HTTPStatus.OK, payload)

    def _detail_response(self, batch_id: str) -> Any:
        detail = self._read_facade.detail_payload(batch_id)
        if detail is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "etc_batch_not_found", "message": f"ETC batch not found: {batch_id}"},
            )
        return self._json_response(HTTPStatus.OK, detail)

    def _delete_response(self, batch_id: str) -> Any:
        business_response = self._legacy_business_delete(batch_id)
        if business_response is not None:
            return business_response
        try:
            result = self._delete_service.delete_non_business_batch(batch_id)
            self._apply_refresh_events(result.refresh_events)
        except EtcBatchNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_batch_not_found", "message": str(error)})
        except EtcBatchDeleteError as error:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "etc_batch_delete_conflict", "message": str(error)},
            )
        except ValueError as error:
            return self._reconciliation_error_response(error)
        return self._json_response(HTTPStatus.OK, result.delete_result)

    def _create_draft_response(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        invoice_ids = payload.get("invoiceIds")
        if not isinstance(invoice_ids, list) or not all(isinstance(item, str) for item in invoice_ids):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_draft_request", "message": "invoiceIds must be a string array."},
            )
        return self._create_draft_from_invoice_ids(invoice_ids, headers)

    def _create_draft_for_batch_response(self, batch_id: str, headers: dict[str, str] | None) -> Any:
        detail = self._read_facade.detail_payload(batch_id)
        if detail is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "etc_batch_not_found", "message": f"ETC batch not found: {batch_id}"},
            )
        summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
        if str(summary.get("status") or "") != "unsubmitted":
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_draft_request", "message": "Only unsubmitted ETC batches can create OA drafts."},
            )
        invoice_items = [item for item in list(detail.get("invoiceItems") or []) if isinstance(item, dict)]
        invoice_ids = [str(item.get("id", "")).strip() for item in invoice_items if str(item.get("id", "")).strip()]
        return self._create_draft_from_invoice_ids(invoice_ids, headers)

    def _create_draft_from_invoice_ids(self, invoice_ids: list[str], headers: dict[str, str] | None) -> Any:
        try:
            result = self._lifecycle_service.create_draft_from_invoice_ids(
                invoice_ids,
                oa_client=self._build_oa_client(headers),
            )
        except EtcInvoiceNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_invoice_not_found", "message": str(error)})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        except EtcOAClientError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_draft_request", "message": str(error)},
            )
        except EtcDraftRequestError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_draft_request", "message": str(error)},
            )
        self._apply_refresh_events(result.refresh_events)
        return self._json_response(HTTPStatus.OK, result.payload)

    def _confirm_submitted_response(self, batch_id: str) -> Any:
        try:
            result = self._lifecycle_service.confirm_submitted(batch_id)
        except EtcBatchNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_batch_not_found", "message": str(error)})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        except EtcDraftRequestError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_batch_request", "message": str(error)},
            )
        self._apply_refresh_events(result.refresh_events)
        return self._json_response(HTTPStatus.OK, result.payload)

    def _mark_not_submitted_response(self, batch_id: str) -> Any:
        try:
            result = self._lifecycle_service.mark_not_submitted(batch_id)
        except EtcBatchNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_batch_not_found", "message": str(error)})
        self._apply_refresh_events(result.refresh_events)
        return self._json_response(HTTPStatus.OK, result.payload)

    def _apply_refresh_events(self, refresh_events: list[Any]) -> None:
        for refresh_event in refresh_events:
            self._refresh_after_etc_invoice_link(
                refresh_event.changed_months,
                reason=refresh_event.reason,
            )
            if getattr(refresh_event, "persist_required", False):
                self._persist_state()
