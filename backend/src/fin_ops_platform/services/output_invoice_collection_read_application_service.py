from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.output_invoice_collection_read_model_detail_service import (
    OutputInvoiceCollectionReadModelDetailService,
)
from fin_ops_platform.services.output_invoice_collection_read_model_fresh_gate_service import (
    OutputInvoiceCollectionReadModelFreshGateService,
)
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionError,
    OutputInvoiceCollectionQueryService,
)


SqlRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | None]
SqlAllRowsProvider = Callable[[dict[str, list[str]]], dict[str, object] | None]
SqlRelationDetailsProvider = Callable[[str, dict[str, list[str]]], dict[str, object] | None]


class OutputInvoiceCollectionReadApplicationService:
    """Read-side application boundary for the output invoice collection page."""

    def __init__(
        self,
        *,
        query_service: OutputInvoiceCollectionQueryService,
        sql_rows_provider: SqlRowsProvider | None = None,
        sql_all_rows_provider: SqlAllRowsProvider | None = None,
        sql_relation_details_provider: SqlRelationDetailsProvider | None = None,
        allow_live_fallback: bool = True,
    ) -> None:
        self._query_service = query_service
        self._sql_rows_provider = sql_rows_provider
        self._sql_all_rows_provider = sql_all_rows_provider
        self._sql_relation_details_provider = sql_relation_details_provider
        self._allow_live_fallback = bool(allow_live_fallback)

    def rows(self, query: dict[str, list[str]], *, tenant_id: str = "default") -> dict[str, Any]:
        sql_payload = self._sql_rows_provider(query) if callable(self._sql_rows_provider) else None
        if isinstance(sql_payload, dict):
            if not self._is_refreshing(sql_payload):
                all_rows_payload = self._all_sql_rows(query)
                sql_payload = self._overlay_rows_payload(
                    sql_payload,
                    tenant_id=tenant_id,
                    summary_rows=list(all_rows_payload.get("rows") or []) if isinstance(all_rows_payload, dict) else None,
                )
            return sql_payload
        if not self._allow_live_fallback:
            return self._refreshing_payload(query)
        return self._query_service.list_rows(
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

    def filter_options(self, query: dict[str, list[str]], *, tenant_id: str = "default") -> dict[str, Any]:
        sql_rows_payload = self._all_sql_rows(query)
        if isinstance(sql_rows_payload, dict):
            if self._is_refreshing(sql_rows_payload):
                return self._with_read_model_alias(sql_rows_payload)
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
            return payload
        if not self._allow_live_fallback:
            return self._refreshing_payload(query)
        return self._query_service.filter_options(
            keyword=query.get("keyword", [None])[0],
            invoice_date_from=query.get("invoice_date_from", [None])[0],
            invoice_date_to=query.get("invoice_date_to", [None])[0],
            month=query.get("month", [None])[0],
            filters=query.get("filters", [None])[0],
            tenant_id=tenant_id,
        )

    def export_preview(self, query: dict[str, list[str]], *, tenant_id: str = "default") -> dict[str, Any]:
        sql_rows_payload = self._all_sql_rows(query)
        if isinstance(sql_rows_payload, dict):
            if self._is_refreshing(sql_rows_payload):
                return self._with_read_model_alias(sql_rows_payload)
            rows = self._query_service.apply_lifecycle_overlays_to_rows(
                [row for row in list(sql_rows_payload.get("rows") or []) if isinstance(row, dict)],
                tenant_id=tenant_id,
            )
            return self._query_service.export_preview_for_rows(rows=rows)
        if not self._allow_live_fallback:
            return self._refreshing_payload(query)
        return self._query_service.export_preview(
            keyword=query.get("keyword", [None])[0],
            invoice_date_from=query.get("invoice_date_from", [None])[0],
            invoice_date_to=query.get("invoice_date_to", [None])[0],
            month=query.get("month", [None])[0],
            filters=query.get("filters", [None])[0],
            sort_field=query.get("sort_field", ["invoice_date"])[0],
            sort_direction=query.get("sort_direction", ["desc"])[0],
            tenant_id=tenant_id,
        )

    def export(self, query: dict[str, list[str]], *, tenant_id: str = "default") -> tuple[str, bytes]:
        sql_rows_payload = self._all_sql_rows(query)
        if isinstance(sql_rows_payload, dict):
            if self._is_refreshing(sql_rows_payload):
                raise OutputInvoiceCollectionError(
                    "output_invoice_collection_read_model_refreshing",
                    "销项发票收款情况数据正在刷新，请稍后重试导出。",
                    status_code=HTTPStatus.CONFLICT,
                    details=self._with_read_model_alias(sql_rows_payload),
                )
            rows = self._query_service.apply_lifecycle_overlays_to_rows(
                [row for row in list(sql_rows_payload.get("rows") or []) if isinstance(row, dict)],
                tenant_id=tenant_id,
            )
            return self._query_service.export_for_rows(rows)
        if not self._allow_live_fallback:
            payload = self._refreshing_payload(query)
            raise OutputInvoiceCollectionError(
                "output_invoice_collection_read_model_refreshing",
                "销项发票收款情况数据正在刷新，请稍后重试导出。",
                status_code=HTTPStatus.CONFLICT,
                details=payload,
            )
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

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        sql_payload = (
            self._sql_relation_details_provider(row_id, query)
            if callable(self._sql_relation_details_provider)
            else None
        )
        if isinstance(sql_payload, dict):
            return sql_payload
        if not self._allow_live_fallback:
            return OutputInvoiceCollectionReadModelDetailService.refreshing_payload(
                kind=query.get("kind", [""])[0],
                scope_key="all",
            )
        return self._query_service.row_relation_details(row_id, kind=query.get("kind", [""])[0])

    def _all_sql_rows(self, query: dict[str, list[str]]) -> dict[str, object] | None:
        return self._sql_all_rows_provider(query) if callable(self._sql_all_rows_provider) else None

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

    @staticmethod
    def _is_refreshing(payload: dict[str, object]) -> bool:
        return str(payload.get("read_model_status") or payload.get("readModelStatus") or "") == "refreshing"

    @staticmethod
    def _with_read_model_alias(payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result["readModelStatus"] = result.get("readModelStatus") or result.get("read_model_status") or "refreshing"
        return result

    @staticmethod
    def _refreshing_payload(query: dict[str, list[str]]) -> dict[str, Any]:
        return OutputInvoiceCollectionReadApplicationService._with_read_model_alias(
            OutputInvoiceCollectionReadModelFreshGateService.refreshing_payload(
                scope_key=OutputInvoiceCollectionReadModelFreshGateService.scope_key_from_query(query),
            )
        )
