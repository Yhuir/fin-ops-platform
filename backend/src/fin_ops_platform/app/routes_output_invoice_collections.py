from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.app.auth import OARequestSession, actor_id_for_session, tenant_id_for_session
from fin_ops_platform.services.output_invoice_collection_lifecycle_service import OutputInvoiceCollectionLifecycleService
from fin_ops_platform.services.output_invoice_collection_receipt_service import OutputInvoiceCollectionReceiptService
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService, OutputInvoiceCollectionError


SqlRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | Any | None]
SqlAllRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | Any | None]


class OutputInvoiceCollectionApiRoutes:
    def __init__(
        self,
        *,
        query_service: OutputInvoiceCollectionQueryService,
        lifecycle_service: OutputInvoiceCollectionLifecycleService,
        receipt_service: OutputInvoiceCollectionReceiptService,
        sql_rows_provider: SqlRowsProvider | None = None,
        sql_all_rows_provider: SqlAllRowsProvider | None = None,
    ) -> None:
        self._query_service = query_service
        self._lifecycle_service = lifecycle_service
        self._receipt_service = receipt_service
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
            invoice_date_from=query.get("invoice_date_from", [None])[0],
            invoice_date_to=query.get("invoice_date_to", [None])[0],
            month=query.get("month", [None])[0],
            filters=query.get("filters", [None])[0],
            sort_field=query.get("sort_field", ["invoice_date"])[0],
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
                invoice_date_from=query.get("invoice_date_from", [None])[0],
                invoice_date_to=query.get("invoice_date_to", [None])[0],
                month=query.get("month", [None])[0],
                filters=query.get("filters", [None])[0],
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
        )

    def status_rules(self, *, session: OARequestSession | None = None) -> dict[str, Any]:
        payload = self._query_service.status_rules()
        payload["permissions"] = {
            "can_save": bool(getattr(session, "can_mutate_data", True)),
            "can_admin": bool(getattr(session, "can_admin_access", False)),
        }
        return payload

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        return self._query_service.invoice_detail(invoice_id)

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        return self._query_service.bank_transaction_detail(bank_transaction_id)

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._query_service.row_relation_details(row_id, kind=query.get("kind", [""])[0])

    def receipt_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        row_id = str(payload.get("rowId") or payload.get("row_id") or "").strip()
        if row_id:
            return self._receipt_service.preview(row_id, payload)
        return self._query_service.receipt_preview(payload)

    def receipt_history(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._query_service.receipt_history(invoice_id=query.get("invoice_id", [""])[0])

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
