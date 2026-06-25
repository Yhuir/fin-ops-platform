from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

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


ReadSessionResolver = Callable[[dict[str, str] | None], tuple[Any | None, Any | None]]
JsonResponse = Callable[[HTTPStatus, object], Any]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]
ErrorResponse = Callable[[PendingInvoiceError], Any]
ExportResponse = Callable[[Any | None, dict[str, list[str]], PendingInvoiceExportFile], Any]


class PendingInvoiceApiRoutes:
    def __init__(
        self,
        *,
        query_service: PendingInvoiceQueryService,
        application_service: PendingInvoiceApplicationService,
        read_model_service: PendingInvoiceReadModelService,
        rules_service: PendingInvoiceRulesApplicationService,
        export_content_type: str,
        resolve_read_session: ReadSessionResolver | None = None,
        json_response: JsonResponse | None = None,
        load_json_body: JsonBodyLoader | None = None,
        error_response: ErrorResponse | None = None,
        export_response: ExportResponse | None = None,
    ) -> None:
        self._query_service = query_service
        self._application_service = application_service
        self._read_model_service = read_model_service
        self._rules_service = rules_service
        self._export_content_type = export_content_type
        self._resolve_read_session = resolve_read_session
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._error_response = error_response
        self._export_response = export_response

    def configure_platform_ports(
        self,
        *,
        resolve_read_session: ReadSessionResolver,
        json_response: JsonResponse,
        load_json_body: JsonBodyLoader,
        error_response: ErrorResponse,
        export_response: ExportResponse,
    ) -> "PendingInvoiceApiRoutes":
        self._resolve_read_session = resolve_read_session
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._error_response = error_response
        self._export_response = export_response
        return self

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/pending-invoices/rows":
            return self._json_read(headers, lambda: self.rows(query))
        if method == "GET" and route_path == "/api/pending-invoices/filter-options":
            return self._json_read(headers, lambda: self.filter_options(query))
        if method == "GET" and route_path == "/api/pending-invoices/invoice-candidates":
            return self._json_read(headers, lambda: (HTTPStatus.OK, self.invoice_candidates(query)))
        if method == "POST" and route_path == "/api/pending-invoices/invoice-candidates/batch":
            return self._json_body_read(body, headers, lambda payload: self.invoice_candidates_batch(payload))
        if method == "GET" and route_path == "/api/pending-invoices/export-preview":
            return self._json_read(headers, lambda: self.export_preview(query))
        if method == "GET" and route_path == "/api/pending-invoices/export":
            return self._export_read(query, headers)
        if method == "GET" and route_path.startswith("/api/pending-invoices/rows/") and route_path.endswith("/relation-detail"):
            transaction_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: (HTTPStatus.OK, self.relation_detail(transaction_id, query)))
        if method == "GET" and route_path.startswith("/api/pending-invoices/bank-transactions/") and route_path.endswith("/detail"):
            bank_transaction_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: (HTTPStatus.OK, self.bank_transaction_detail(bank_transaction_id)))
        if method == "GET" and route_path.startswith("/api/pending-invoices/invoices/") and route_path.endswith("/detail"):
            invoice_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: (HTTPStatus.OK, self.invoice_detail(invoice_id)))
        if method == "GET" and route_path.startswith("/api/pending-invoices/oa/") and route_path.endswith("/detail"):
            oa_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda: (HTTPStatus.OK, self.oa_detail(oa_id)))
        return None

    def rows(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        payload = self._read_model_service.rows(query)
        return _read_model_status_code(payload), payload

    def filter_options(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        options_payload = self._read_model_service.filter_options(query)
        if options_payload.get("read_model_status") != "fresh":
            return HTTPStatus.ACCEPTED, options_payload
        payload = self._query_service.filter_options_for_rows(
            rows=list(options_payload.get("rows") or []),
            direction=str(options_payload.get("direction") or query.get("direction", ["expense"])[0]),
            filter=str(options_payload.get("filter") or query.get("filter", ["all"])[0]),
        )
        if isinstance(options_payload.get("options"), dict):
            payload["options"] = options_payload["options"]
        payload["read_model_status"] = "fresh"
        payload["read_model_scope_key"] = options_payload.get("read_model_scope_key")
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

    def invoice_candidates_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._query_service.invoice_candidates_batch(
            transaction_ids=list(payload.get("transaction_ids") or []),
            keyword=payload.get("keyword"),
            seller_name=payload.get("seller_name"),
            issue_date_from=payload.get("issue_date_from"),
            issue_date_to=payload.get("issue_date_to"),
            amount_min=payload.get("amount_min"),
            amount_max=payload.get("amount_max"),
            sort_field=payload.get("sort_field"),
            sort_direction=payload.get("sort_direction"),
            page=payload.get("page", 1),
            page_size=payload.get("page_size", 50),
        )

    def relation_detail(self, transaction_id: str, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        request_query = query or {}
        return self._query_service.relation_detail(
            transaction_id=transaction_id,
            direction=request_query.get("direction", ["expense"])[0],
            kind=request_query.get("kind", ["all"])[0],
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

    def attach_existing_batch_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._application_service.preview_attach_existing_invoices(payload=payload)

    def attach_existing_batch_confirm(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有选择已有发票权限。")
        return self._application_service.confirm_attach_existing_invoices(
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

    def update_income_statuses(
        self,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有批量标记收入流水开票状态权限。")
        return self._application_service.confirm_income_status_overrides(
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

    @staticmethod
    def _require_mutation(session: OARequestSession | None, message: str) -> None:
        if not bool(getattr(session, "can_mutate_data", True)):
            raise PendingInvoiceError("permission_denied", message, status_code=HTTPStatus.FORBIDDEN)

    def _json_read(self, headers: dict[str, str] | None, action: Callable[[], tuple[HTTPStatus, dict[str, Any]]]) -> Any:
        _session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            status_code, payload = action()
        except PendingInvoiceError as exc:
            return self._error(exc)
        return self._json(status_code, payload)

    def _json_body_read(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        action: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> Any:
        if not callable(self._load_json_body):
            raise RuntimeError("Pending invoice body loader is not configured.")
        _session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            result = action(payload)
        except PendingInvoiceError as exc:
            return self._error(exc)
        return self._json(HTTPStatus.OK, result)

    def _export_read(self, query: dict[str, list[str]], headers: dict[str, str] | None) -> Any:
        session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            status_code, result = self.export(query)
        except PendingInvoiceError as exc:
            return self._error(exc)
        if not isinstance(result, PendingInvoiceExportFile):
            return self._json(status_code, result)
        if not callable(self._export_response):
            return status_code, result
        return self._export_response(session, query, result)

    def _read_session(self, headers: dict[str, str] | None) -> tuple[Any | None, Any | None]:
        if not callable(self._resolve_read_session):
            return None, None
        return self._resolve_read_session(headers)

    def _json(self, status_code: HTTPStatus, payload: object) -> Any:
        if not callable(self._json_response):
            return status_code, payload
        return self._json_response(status_code, payload)

    def _error(self, exc: PendingInvoiceError) -> Any:
        if callable(self._error_response):
            return self._error_response(exc)
        raise exc


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
