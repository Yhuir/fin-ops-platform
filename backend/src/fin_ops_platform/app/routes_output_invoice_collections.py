from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.app.auth import OARequestSession, actor_id_for_session, tenant_id_for_session
from fin_ops_platform.services.output_invoice_collection_lifecycle_service import OutputInvoiceCollectionLifecycleService
from fin_ops_platform.services.output_invoice_collection_receipt_service import OutputInvoiceCollectionReceiptService
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService, OutputInvoiceCollectionError


SqlRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | Any | None]
SqlAllRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | Any | None]
SqlRelationDetailsProvider = Callable[[str, dict[str, list[str]]], dict[str, object] | None]
ReadSessionResolver = Callable[[dict[str, str] | None], tuple[OARequestSession | None, Any | None]]
JsonResponse = Callable[[HTTPStatus, object], Any]
XlsxResponse = Callable[[str, bytes], Any]
ErrorResponse = Callable[[OutputInvoiceCollectionError], Any]


class OutputInvoiceCollectionApiRoutes:
    def __init__(
        self,
        *,
        query_service: OutputInvoiceCollectionQueryService,
        lifecycle_service: OutputInvoiceCollectionLifecycleService,
        receipt_service: OutputInvoiceCollectionReceiptService,
        sql_rows_provider: SqlRowsProvider | None = None,
        sql_all_rows_provider: SqlAllRowsProvider | None = None,
        sql_relation_details_provider: SqlRelationDetailsProvider | None = None,
        resolve_read_session: ReadSessionResolver | None = None,
        json_response: JsonResponse | None = None,
        xlsx_response: XlsxResponse | None = None,
        error_response: ErrorResponse | None = None,
    ) -> None:
        self._query_service = query_service
        self._lifecycle_service = lifecycle_service
        self._receipt_service = receipt_service
        self._sql_rows_provider = sql_rows_provider
        self._sql_all_rows_provider = sql_all_rows_provider
        self._sql_relation_details_provider = sql_relation_details_provider
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
            return self._json_read(headers, lambda session: self.rows(query, session=session))
        if method == "GET" and route_path == "/api/output-invoice-collections/filter-options":
            return self._json_read(headers, lambda session: self.filter_options(query, session=session))
        if method == "GET" and route_path == "/api/output-invoice-collections/export-preview":
            return self._json_read(headers, lambda session: self.export_preview(query, session=session))
        if method == "GET" and route_path == "/api/output-invoice-collections/export":
            session, auth_error = self._read_session(headers)
            if auth_error is not None:
                return auth_error
            try:
                filename, content = self.export(query, session=session)
            except OutputInvoiceCollectionError as exc:
                return self._error(exc)
            return self._xlsx(filename, content)
        if method == "GET" and route_path == "/api/output-invoice-collections/status-rules":
            return self._json_read(headers, lambda session: (HTTPStatus.OK, self.status_rules(session=session)))
        if method == "GET" and route_path == "/api/output-invoice-collections/receipts/history":
            return self._json_read(headers, lambda session: (HTTPStatus.OK, self.receipt_history(query, session=session)))
        if method == "GET" and route_path.startswith("/api/output-invoice-collections/invoices/") and route_path.endswith("/detail"):
            invoice_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda session: (HTTPStatus.OK, self.invoice_detail(invoice_id, session=session)))
        if method == "GET" and route_path.startswith("/api/output-invoice-collections/bank-transactions/") and route_path.endswith("/detail"):
            bank_transaction_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._json_read(headers, lambda session: (HTTPStatus.OK, self.bank_transaction_detail(bank_transaction_id, session=session)))
        if method == "GET" and route_path.startswith("/api/output-invoice-collections/rows/") and route_path.endswith("/relation-details"):
            row_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._relation_details_response(headers, row_id, query)
        return None

    def rows(self, query: dict[str, list[str]], *, session: OARequestSession | None = None) -> tuple[HTTPStatus, dict[str, Any]]:
        tenant_id = _tenant_id(session)
        sql_payload = self._sql_rows_provider(query) if callable(self._sql_rows_provider) else None
        if isinstance(sql_payload, dict):
            status_code = HTTPStatus.ACCEPTED if sql_payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
            if status_code == HTTPStatus.OK:
                all_rows_payload = self._sql_all_rows_provider(query) if callable(self._sql_all_rows_provider) else None
                sql_payload = self._overlay_rows_payload(
                    sql_payload,
                    tenant_id=tenant_id,
                    summary_rows=list(all_rows_payload.get("rows") or []) if isinstance(all_rows_payload, dict) else None,
                )
            return status_code, sql_payload
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
            tenant_id=tenant_id,
        )
        return HTTPStatus.OK, payload

    def filter_options(self, query: dict[str, list[str]], *, session: OARequestSession | None = None) -> tuple[HTTPStatus, dict[str, Any]]:
        tenant_id = _tenant_id(session)
        sql_rows_payload = self._sql_all_rows_provider(query) if callable(self._sql_all_rows_provider) else None
        if _is_response_like(sql_rows_payload):
            return HTTPStatus.ACCEPTED, _response_like_payload(sql_rows_payload)
        if isinstance(sql_rows_payload, dict):
            payload = self._query_service.filter_options_for_rows(
                rows=list(sql_rows_payload.get("rows") or []),
                keyword=query.get("keyword", [None])[0],
                invoice_date_from=query.get("invoice_date_from", [None])[0],
                invoice_date_to=query.get("invoice_date_to", [None])[0],
                month=query.get("month", [None])[0],
                filters=query.get("filters", [None])[0],
                tenant_id=tenant_id,
            )
            payload["read_model_status"] = "fresh"
            payload["read_model_scope_key"] = sql_rows_payload.get("read_model_scope_key")
            payload["readModelStatus"] = "fresh"
            return HTTPStatus.OK, payload
        return HTTPStatus.OK, self._query_service.filter_options(
            keyword=query.get("keyword", [None])[0],
            invoice_date_from=query.get("invoice_date_from", [None])[0],
            invoice_date_to=query.get("invoice_date_to", [None])[0],
            month=query.get("month", [None])[0],
            filters=query.get("filters", [None])[0],
            tenant_id=tenant_id,
        )

    def export_preview(self, query: dict[str, list[str]], *, session: OARequestSession | None = None) -> tuple[HTTPStatus, dict[str, Any]]:
        tenant_id = _tenant_id(session)
        sql_rows_payload = self._sql_all_rows_provider(query) if callable(self._sql_all_rows_provider) else None
        if _is_response_like(sql_rows_payload):
            payload = _response_like_payload(sql_rows_payload)
            payload["readModelStatus"] = payload.get("readModelStatus") or payload.get("read_model_status") or "refreshing"
            return HTTPStatus.ACCEPTED, payload
        if isinstance(sql_rows_payload, dict):
            rows = self._query_service.apply_lifecycle_overlays_to_rows(
                [row for row in list(sql_rows_payload.get("rows") or []) if isinstance(row, dict)],
                tenant_id=tenant_id,
            )
            return HTTPStatus.OK, self._query_service.export_preview_for_rows(rows=rows)
        return HTTPStatus.OK, self._query_service.export_preview(
            keyword=query.get("keyword", [None])[0],
            invoice_date_from=query.get("invoice_date_from", [None])[0],
            invoice_date_to=query.get("invoice_date_to", [None])[0],
            month=query.get("month", [None])[0],
            filters=query.get("filters", [None])[0],
            sort_field=query.get("sort_field", ["invoice_date"])[0],
            sort_direction=query.get("sort_direction", ["desc"])[0],
            tenant_id=tenant_id,
        )

    def export(self, query: dict[str, list[str]], *, session: OARequestSession | None = None) -> tuple[str, bytes]:
        tenant_id = _tenant_id(session)
        sql_rows_payload = self._sql_all_rows_provider(query) if callable(self._sql_all_rows_provider) else None
        if _is_response_like(sql_rows_payload):
            raise OutputInvoiceCollectionError(
                "output_invoice_collection_read_model_refreshing",
                "销项发票收款情况数据正在刷新，请稍后重试导出。",
                status_code=HTTPStatus.CONFLICT,
                details=_response_like_payload(sql_rows_payload),
            )
        if isinstance(sql_rows_payload, dict):
            rows = self._query_service.apply_lifecycle_overlays_to_rows(
                [row for row in list(sql_rows_payload.get("rows") or []) if isinstance(row, dict)],
                tenant_id=tenant_id,
            )
            return self._query_service.export_for_rows(rows)
        return self._query_service.export(
            keyword=query.get("keyword", [None])[0],
            invoice_date_from=query.get("invoice_date_from", [None])[0],
            invoice_date_to=query.get("invoice_date_to", [None])[0],
            month=query.get("month", [None])[0],
            filters=query.get("filters", [None])[0],
            sort_field=query.get("sort_field", ["invoice_date"])[0],
            sort_direction=query.get("sort_direction", ["desc"])[0],
            tenant_id=tenant_id,
        )

    def status_rules(self, *, session: OARequestSession | None = None) -> dict[str, Any]:
        payload = self._query_service.status_rules()
        payload["permissions"] = {
            "can_save": bool(getattr(session, "can_mutate_data", True)),
            "can_admin": bool(getattr(session, "can_admin_access", False)),
        }
        return payload

    def invoice_detail(self, invoice_id: str, *, session: OARequestSession | None = None) -> dict[str, Any]:
        return self._query_service.invoice_detail(invoice_id)

    def bank_transaction_detail(self, bank_transaction_id: str, *, session: OARequestSession | None = None) -> dict[str, Any]:
        return self._query_service.bank_transaction_detail(bank_transaction_id)

    def relation_details(
        self,
        row_id: str,
        query: dict[str, list[str]],
        *,
        session: OARequestSession | None = None,
    ) -> dict[str, Any]:
        sql_payload = (
            self._sql_relation_details_provider(row_id, query)
            if callable(self._sql_relation_details_provider)
            else None
        )
        if isinstance(sql_payload, dict):
            return sql_payload
        return self._query_service.row_relation_details(row_id, kind=query.get("kind", [""])[0])

    def receipt_preview(self, payload: dict[str, Any], *, session: OARequestSession | None = None) -> dict[str, Any]:
        row_id = str(payload.get("rowId") or payload.get("row_id") or "").strip()
        if row_id:
            return self._receipt_service.preview(row_id, payload)
        return self._query_service.receipt_preview(payload, tenant_id=_tenant_id(session))

    def receipt_history(self, query: dict[str, list[str]], *, session: OARequestSession | None = None) -> dict[str, Any]:
        return self._query_service.receipt_history(invoice_id=query.get("invoice_id", [""])[0], tenant_id=_tenant_id(session))

    def set_collection_status(
        self,
        row_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有设置销项发票收款状态权限。")
        return self._lifecycle_service.set_collection_status(
            row_id,
            payload,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def upsert_collection_reminder(
        self,
        row_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有设置销项发票收款提醒权限。")
        return self._lifecycle_service.upsert_collection_reminder(
            row_id,
            payload,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def cancel_collection_reminder(
        self,
        row_id: str,
        reminder_id: str,
        *,
        session: OARequestSession | None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有取消销项发票收款提醒权限。")
        return self._lifecycle_service.cancel_collection_reminder(
            row_id,
            reminder_id,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def confirm_red_invoice_relation(
        self,
        row_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有确认红蓝票关系权限。")
        return self._lifecycle_service.confirm_red_invoice_relation(
            row_id,
            payload,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def revoke_red_invoice_relation(
        self,
        relation_id: str,
        *,
        session: OARequestSession | None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有撤销红蓝票关系权限。")
        return self._lifecycle_service.revoke_red_invoice_relation(
            relation_id,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def create_receipt(
        self,
        row_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有创建正式收据权限。")
        body = dict(payload or {})
        if idempotency_key and not body.get("idempotencyKey"):
            body["idempotencyKey"] = idempotency_key
        return self._receipt_service.create_receipt(
            row_id,
            body,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def void_receipt(
        self,
        receipt_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有作废正式收据权限。")
        return self._receipt_service.void_receipt(
            receipt_id,
            payload,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def reissue_receipt(
        self,
        receipt_id: str,
        payload: dict[str, Any],
        *,
        session: OARequestSession | None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_mutation(session, "当前账户没有重开正式收据权限。")
        return self._receipt_service.reissue_receipt(
            receipt_id,
            payload,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
            trace_id=trace_id,
        )

    def get_receipt_settings(self, *, session: OARequestSession | None) -> dict[str, Any]:
        self._require_admin(session)
        return self._receipt_service.get_settings(tenant_id=_tenant_id(session))

    def update_receipt_settings(self, payload: dict[str, Any], *, session: OARequestSession | None) -> dict[str, Any]:
        self._require_admin(session)
        return self._receipt_service.update_settings(
            payload,
            actor_id=_actor_id(session),
            tenant_id=_tenant_id(session),
        )

    @staticmethod
    def _require_mutation(session: OARequestSession | None, message: str) -> None:
        if session is None:
            return
        if not getattr(session, "can_mutate_data", False):
            raise OutputInvoiceCollectionError("permission_denied", message, status_code=HTTPStatus.FORBIDDEN)

    @staticmethod
    def _require_admin(session: OARequestSession | None) -> None:
        if session is None:
            return
        if not getattr(session, "can_admin_access", False):
            raise OutputInvoiceCollectionError("admin_only", "当前账户没有维护收据编号设置权限。", status_code=HTTPStatus.FORBIDDEN)

    def _overlay_rows_payload(
        self,
        payload: dict[str, Any],
        *,
        tenant_id: str,
        summary_rows: list[Any] | None = None,
    ) -> dict[str, Any]:
        rows = self._query_service.apply_lifecycle_overlays_to_rows(
            [row for row in list(payload.get("rows") or []) if isinstance(row, dict)],
            tenant_id=tenant_id,
        )
        result = dict(payload)
        result["rows"] = rows
        if summary_rows is not None:
            typed_summary_rows = [row for row in summary_rows if isinstance(row, dict)]
            result["summary"] = self._query_service.summary_for_rows(
                self._query_service.apply_lifecycle_overlays_to_rows(typed_summary_rows, tenant_id=tenant_id)
            )
        return result

    def _json_read(
        self,
        headers: dict[str, str] | None,
        callback: Callable[[OARequestSession | None], tuple[HTTPStatus, dict[str, Any]]],
    ) -> Any:
        session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            status_code, payload = callback(session)
        except OutputInvoiceCollectionError as exc:
            return self._error(exc)
        return self._json(status_code, payload)

    def _relation_details_response(
        self,
        headers: dict[str, str] | None,
        row_id: str,
        query: dict[str, list[str]],
    ) -> Any:
        session, auth_error = self._read_session(headers)
        if auth_error is not None:
            return auth_error
        try:
            payload = self.relation_details(row_id, query, session=session)
        except OutputInvoiceCollectionError as exc:
            return self._error(exc)
        status_code = HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
        return self._json(status_code, payload)

    def _read_session(self, headers: dict[str, str] | None) -> tuple[OARequestSession | None, Any | None]:
        if callable(self._resolve_read_session):
            return self._resolve_read_session(headers)
        return None, None

    def _json(self, status: HTTPStatus, payload: object) -> Any:
        if not callable(self._json_response):
            raise RuntimeError("output invoice collection json response port is not configured")
        return self._json_response(status, payload)

    def _xlsx(self, filename: str, content: bytes) -> Any:
        if not callable(self._xlsx_response):
            raise RuntimeError("output invoice collection xlsx response port is not configured")
        return self._xlsx_response(filename, content)

    def _error(self, exc: OutputInvoiceCollectionError) -> Any:
        if not callable(self._error_response):
            raise exc
        return self._error_response(exc)


def _is_response_like(value: Any) -> bool:
    return hasattr(value, "status_code") and hasattr(value, "body")


def _response_like_payload(value: Any) -> dict[str, Any]:
    import json

    try:
        return json.loads(value.body)
    except Exception:
        return {"read_model_status": "refreshing"}


def _actor_id(session: OARequestSession | None) -> str:
    return actor_id_for_session(session) if session is not None else "local"


def _tenant_id(session: OARequestSession | None) -> str:
    return tenant_id_for_session(session) if session is not None else "default"
