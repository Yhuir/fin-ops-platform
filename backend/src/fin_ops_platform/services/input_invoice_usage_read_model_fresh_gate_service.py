from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.input_invoice_usage_read_model_detail_service import (
    InputInvoiceUsageReadModelDetailService,
)
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    InputInvoiceUsageQueryService,
)
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)


class InputInvoiceUsageReadModelFreshGateService:
    def __init__(
        self,
        *,
        repository: Any | None,
        query_service: InputInvoiceUsageQueryService,
        requires_sql_read_model_runtime: Callable[[], bool],
        enqueue_refresh: Callable[[str, str], bool],
        expected_source_versions: Callable[..., dict[str, object]],
    ) -> None:
        self._repository = repository
        self._query_service = query_service
        self._requires_sql_read_model_runtime = requires_sql_read_model_runtime
        self._enqueue_refresh = enqueue_refresh
        self._expected_source_versions = expected_source_versions

    def export_page(self, **kwargs: object) -> dict[str, object] | None:
        query = self.export_query_from_kwargs(kwargs)
        sql_payload = self.rows(query)
        if sql_payload is not None:
            return sql_payload
        return self._query_service.list_rows(
            page=kwargs.get("page") or 1,
            page_size=kwargs.get("page_size") or 50,
            keyword=kwargs.get("keyword"),
            invoice_date_from=kwargs.get("invoice_date_from"),
            invoice_date_to=kwargs.get("invoice_date_to"),
            month=kwargs.get("month"),
            filters=kwargs.get("filters"),
            sort_field=kwargs.get("sort_field") or "invoice_date",
            sort_direction=kwargs.get("sort_direction") or "desc",
        )

    def all_rows(self, query: dict[str, list[str]]) -> dict[str, object] | None:
        page_size = 200
        first_query = {key: list(values) for key, values in query.items()}
        first_query["page"] = ["1"]
        first_query["page_size"] = [str(page_size)]
        first_payload = self.rows(first_query)
        if first_payload is None:
            return None
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
            if not isinstance(page_payload, dict):
                return None
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
            "read_model_status": "fresh",
            "read_model_scope_key": first_payload.get("read_model_scope_key"),
        }

    def rows(self, query: dict[str, list[str]]) -> dict[str, object] | None:
        list_rows = getattr(self._repository, "list_input_invoice_usage_rows", None)
        scope_key = self.scope_key_from_query(query)
        if not callable(list_rows):
            if self._requires_sql_read_model_runtime():
                self._enqueue_refresh(scope_key, "api_sql_repository_unavailable")
                return self.refreshing_payload(scope_key=scope_key)
            return None
        try:
            payload = list_rows(
                month=query.get("month", [None])[0],
                keyword=query.get("keyword", [None])[0],
                invoice_date_from=query.get("invoice_date_from", [None])[0],
                invoice_date_to=query.get("invoice_date_to", [None])[0],
                filters=query.get("filters", [None])[0],
                sort_field=query.get("sort_field", ["invoice_date"])[0],
                sort_direction=query.get("sort_direction", ["desc"])[0],
                page=query.get("page", [1])[0],
                page_size=query.get("page_size", [50])[0],
            )
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_input_invoice_usage_query", str(exc)) from exc
        if not isinstance(payload, dict):
            self._enqueue_refresh(scope_key, "api_miss")
            return self.refreshing_payload(scope_key=scope_key)
        if self.payload_requires_schema_refresh(payload):
            self._enqueue_refresh(scope_key, "api_schema_stale")
            return self.refreshing_payload(scope_key=scope_key)
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            self._enqueue_refresh(scope_key, "api_stale")
            return self.refreshing_payload(scope_key=scope_key)
        stale_reasons = source_version_mismatch_reasons(
            expected=require_expected_source_versions(
                self._expected_source_versions(scope_key=scope_key),
                context="input_invoice_usage_read_model",
            ),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            self._enqueue_refresh(scope_key, "api_source_versions_stale")
            return self.refreshing_payload(scope_key=scope_key, stale_reasons=stale_reasons)
        parsed_filters = self._query_service._parse_filters(query.get("filters", [None])[0])
        sort_field, sort_direction = self._query_service._parse_sort(
            query.get("sort_field", ["invoice_date"])[0],
            query.get("sort_direction", ["desc"])[0],
        )
        result = dict(payload)
        result["filterConfig"] = self._query_service._filter_config()
        result["appliedFilters"] = {"filters": parsed_filters}
        result["sort"] = {"field": sort_field, "direction": sort_direction}
        result["read_model_status"] = "fresh"
        result["read_model_scope_key"] = scope_key
        result.pop("refresh_status", None)
        return result

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> dict[str, object] | None:
        if not callable(getattr(self._repository, "get_input_invoice_usage_row_by_row_id", None)):
            if self._requires_sql_read_model_runtime():
                self._enqueue_refresh("all", "api_detail_sql_repository_unavailable")
                return InputInvoiceUsageReadModelDetailService.refreshing_payload(
                    kind=query.get("kind", [""])[0],
                    scope_key="all",
                )
            return None
        service = InputInvoiceUsageReadModelDetailService(
            repository=self._repository,
            enqueue_refresh=self._enqueue_refresh,
            source_versions_provider=self._expected_source_versions,
        )
        return service.relation_details(row_id, kind=query.get("kind", [""])[0])

    @staticmethod
    def export_query_from_kwargs(kwargs: dict[str, object]) -> dict[str, list[str]]:
        query: dict[str, list[str]] = {}
        for key in ("month", "keyword", "invoice_date_from", "invoice_date_to", "filters", "sort_field", "sort_direction", "page", "page_size"):
            value = kwargs.get(key)
            if value not in (None, ""):
                query[key] = [str(value)]
        return query

    @staticmethod
    def payload_requires_schema_refresh(payload: dict[str, object]) -> bool:
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                return True
            if not isinstance(row.get("invoice"), dict):
                return True
            if not isinstance(row.get("paymentStatus"), dict):
                return True
            if not isinstance(row.get("oa"), dict):
                return True
            if not isinstance(row.get("bankTransactions"), dict):
                return True
        return False

    @staticmethod
    def scope_key_from_query(query: dict[str, list[str]]) -> str:
        month = str(query.get("month", [""])[0] or "").strip()
        if len(month) >= 7 and month[4] == "-":
            return month[:7]
        return "all"

    @staticmethod
    def refreshing_payload(
        *,
        scope_key: str,
        stale_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "rows": [],
            "pagination": {"page": 1, "pageSize": 50, "total": 0},
            "summary": {},
            "filterConfig": [],
            "read_model_status": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload
