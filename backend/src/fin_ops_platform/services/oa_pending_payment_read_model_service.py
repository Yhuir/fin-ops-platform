from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.oa_pending_payment_read_model_details import (
    oa_pending_payment_bank_detail_from_row,
    oa_pending_payment_invoice_detail_from_row,
    oa_pending_payment_oa_detail_from_row,
    oa_pending_payment_relation_details_from_row,
)
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentError, OaPendingPaymentQueryService
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


SourceVersionsProvider = Callable[[], dict[str, Any]]


class OaPendingPaymentReadModelService:
    def __init__(
        self,
        *,
        repository: Any | None,
        queue_repository: Any | None = None,
        query_service: OaPendingPaymentQueryService,
        source_versions_provider: SourceVersionsProvider | None = None,
    ) -> None:
        self._repository = repository
        self._queue_repository = queue_repository
        self._query_service = query_service
        self._source_versions_provider = source_versions_provider

    def rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        scope_key = self._scope_key_from_query(query)
        view_mode = OaPendingPaymentQueryService._parse_view_mode(query.get("view_mode", [None])[0])
        list_rows = getattr(self._repository, "list_oa_pending_payment_rows", None)
        if not callable(list_rows):
            self._enqueue_refresh(scope_key, reason="api_sql_repository_unavailable")
            return self.refreshing_rows_payload(scope_key=scope_key)
        try:
            payload = list_rows(
                month=query.get("month", [None])[0],
                keyword=query.get("keyword", [None])[0],
                trade_date_from=query.get("trade_date_from", [None])[0],
                trade_date_to=query.get("trade_date_to", [None])[0],
                filters=query.get("filters", [None])[0],
                sort_field=query.get("sort_field", ["bank_trade_time"])[0],
                sort_direction=query.get("sort_direction", ["desc"])[0],
                page=query.get("page", [1])[0],
                page_size=query.get("page_size", [50])[0],
                view_mode=view_mode,
            )
        except ValueError as exc:
            raise OaPendingPaymentError("invalid_oa_pending_payment_query", str(exc)) from exc
        if not isinstance(payload, dict):
            self._enqueue_refresh(scope_key, reason="api_miss")
            return self.refreshing_rows_payload(scope_key=scope_key)

        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            self._enqueue_refresh(scope_key, reason="api_stale")
            return self.refreshing_rows_payload(scope_key=scope_key)

        stale_reasons = source_version_mismatch_reasons(
            expected=self.expected_source_versions(scope_key=scope_key),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            self._enqueue_refresh(scope_key, reason="api_source_versions_stale")
            return self.refreshing_rows_payload(scope_key=scope_key, stale_reasons=stale_reasons)

        result = dict(payload)
        parsed_filters = self._query_service._parse_filters(query.get("filters", [None])[0])
        sort_field, sort_direction = self._query_service._parse_sort(
            query.get("sort_field", ["bank_trade_time"])[0],
            query.get("sort_direction", ["desc"])[0],
        )
        result["filterConfig"] = self._query_service._filter_config()
        result["appliedFilters"] = {"filters": parsed_filters}
        result["sort"] = {"field": sort_field, "direction": sort_direction}
        result["viewMode"] = view_mode
        result["read_model_status"] = "fresh"
        result["readModelStatus"] = "fresh"
        result["read_model_scope_key"] = scope_key
        result.pop("refresh_status", None)
        return result

    def all_rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        page_size = 200
        first_query = {key: list(values) for key, values in query.items()}
        first_query["page"] = ["1"]
        first_query["page_size"] = [str(page_size)]
        first_payload = self.rows(first_query)
        if first_payload.get("read_model_status") != "fresh":
            return first_payload
        rows = list(first_payload.get("rows") or [])
        pagination = first_payload.get("pagination") if isinstance(first_payload.get("pagination"), dict) else {}
        total = int(pagination.get("total") or len(rows))
        page = 2
        while len(rows) < total:
            page_query = {key: list(values) for key, values in query.items()}
            page_query["page"] = [str(page)]
            page_query["page_size"] = [str(page_size)]
            page_payload = self.rows(page_query)
            if page_payload.get("read_model_status") != "fresh":
                return page_payload
            page_rows = list(page_payload.get("rows") or [])
            if not page_rows:
                break
            rows.extend(page_rows)
            page += 1
        return {
            "rows": rows,
            "pagination": {"page": 1, "pageSize": page_size, "total": total},
            "summary": first_payload.get("summary") if isinstance(first_payload.get("summary"), dict) else {},
            "viewMode": first_payload.get("viewMode"),
            "read_model_status": "fresh",
            "readModelStatus": "fresh",
            "read_model_scope_key": first_payload.get("read_model_scope_key"),
        }

    def filter_options(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        rows_payload = self.all_rows(query)
        if rows_payload.get("read_model_status") != "fresh":
            return HTTPStatus.ACCEPTED, rows_payload
        payload = self._query_service.filter_options_for_rows(
            rows=list(rows_payload.get("rows") or []),
            keyword=query.get("keyword", [None])[0],
            month=query.get("month", [None])[0],
            trade_date_from=query.get("trade_date_from", [None])[0],
            trade_date_to=query.get("trade_date_to", [None])[0],
            filters=query.get("filters", [None])[0],
            view_mode=query.get("view_mode", [None])[0],
        )
        payload["read_model_status"] = "fresh"
        payload["readModelStatus"] = "fresh"
        payload["read_model_scope_key"] = rows_payload.get("read_model_scope_key")
        return HTTPStatus.OK, payload

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_oa_id",
            identifier=oa_id,
            builder=oa_pending_payment_oa_detail_from_row,
            not_found_code="oa_not_found",
            not_found_message=f"OA detail not found: {oa_id}",
            title="OA详情",
        )

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_bank_transaction_id",
            identifier=bank_transaction_id,
            builder=lambda row: oa_pending_payment_bank_detail_from_row(row, bank_transaction_id),
            not_found_code="bank_transaction_not_found",
            not_found_message=f"Bank transaction detail not found: {bank_transaction_id}",
            title="支出流水详情",
        )

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_invoice_id",
            identifier=invoice_id,
            builder=lambda row: oa_pending_payment_invoice_detail_from_row(row, invoice_id),
            not_found_code="invoice_not_found",
            not_found_message=f"Invoice detail not found: {invoice_id}",
            title="发票详情",
        )

    def relation_details(self, row_id: str, *, kind: str) -> dict[str, Any]:
        title = "支出流水关联明细" if kind == "bank" else "发票关联明细"
        return self._detail(
            lookup_method_name="get_oa_pending_payment_row_by_row_id",
            identifier=row_id,
            builder=lambda row: oa_pending_payment_relation_details_from_row(row, kind=kind),
            not_found_code="row_not_found",
            not_found_message=f"OA pending payment row not found: {row_id}",
            title=title,
        )

    def expected_source_versions(self, *, scope_key: str | None = None) -> dict[str, Any]:
        if not callable(self._source_versions_provider):
            return require_expected_source_versions({}, context="oa_pending_payment_read_model")
        return require_expected_source_versions(
            _source_versions_from_provider(self._source_versions_provider, scope_key=scope_key) or {},
            context="oa_pending_payment_read_model",
        )

    def refreshing_rows_payload(self, *, scope_key: str, stale_reasons: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rows": [],
            "pagination": {"page": 1, "pageSize": 50, "total": 0},
            "summary": {"rowCount": 0, "viewCounts": {"completed": 0, "in_progress": 0}},
            "filterConfig": [],
            "read_model_status": "refreshing",
            "readModelStatus": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload

    def _detail(
        self,
        *,
        lookup_method_name: str,
        identifier: str,
        builder: Callable[[dict[str, Any]], dict[str, Any]],
        not_found_code: str,
        not_found_message: str,
        title: str,
    ) -> dict[str, Any]:
        lookup = getattr(self._repository, lookup_method_name, None)
        if not callable(lookup):
            self._enqueue_refresh("all", reason="api_detail_sql_repository_unavailable")
            return self._refreshing_detail_payload(title=title, scope_key="all")
        payload = lookup(identifier)
        if not isinstance(payload, dict):
            self._enqueue_refresh("all", reason="api_detail_miss")
            return self._refreshing_detail_payload(title=title, scope_key="all")
        scope_key = str(payload.get("read_model_scope_key") or "all")
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            self._enqueue_refresh(scope_key, reason="api_detail_stale")
            return self._refreshing_detail_payload(title=title, scope_key=scope_key)
        stale_reasons = source_version_mismatch_reasons(
            expected=self.expected_source_versions(scope_key=scope_key),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            self._enqueue_refresh(scope_key, reason="api_detail_source_versions_stale")
            return self._refreshing_detail_payload(title=title, scope_key=scope_key, stale_reasons=stale_reasons)
        row = payload.get("row")
        if not isinstance(row, dict):
            raise OaPendingPaymentError(not_found_code, not_found_message, status_code=HTTPStatus.NOT_FOUND)
        try:
            detail_payload = builder(row)
        except ValueError as exc:
            raise OaPendingPaymentError("invalid_relation_kind", str(exc)) from exc
        if not isinstance(detail_payload, dict):
            raise OaPendingPaymentError(not_found_code, not_found_message, status_code=HTTPStatus.NOT_FOUND)
        detail_payload["read_model_status"] = "fresh"
        detail_payload["readModelStatus"] = "fresh"
        detail_payload["read_model_scope_key"] = scope_key
        return detail_payload

    @staticmethod
    def _refreshing_detail_payload(
        *,
        title: str,
        scope_key: str,
        stale_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "detailAvailable": False,
            "unavailableReason": "详情数据正在刷新，请稍后重试。",
            "sections": [],
            "read_model_status": "refreshing",
            "readModelStatus": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload

    @staticmethod
    def _scope_key_from_query(query: dict[str, list[str]]) -> str:
        month = str(query.get("month", [""])[0] or "").strip()
        if len(month) >= 7 and month[4] == "-":
            return month[:7]
        return "all"

    def _enqueue_refresh(self, scope_key: str, *, reason: str) -> bool:
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return False
        return bool(refresh_gateway.enqueue_one("oa_pending_payment", scope_key, reason=reason))


def _source_versions_from_provider(provider: SourceVersionsProvider, *, scope_key: str | None) -> dict[str, Any]:
    try:
        return dict(provider(scope_key=scope_key) or {})  # type: ignore[misc]
    except TypeError:
        return dict(provider() or {})
