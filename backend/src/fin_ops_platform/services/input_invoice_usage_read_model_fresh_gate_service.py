from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.input_invoice_usage_read_model_detail_service import (
    InputInvoiceUsageReadModelDetailService,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageError
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)


class InputInvoiceUsageReadModelFreshGateService:
    def __init__(
        self,
        *,
        repository: Any | None,
        query_service: Any | None,
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
        scope_key = self.scope_key_from_query(query)
        self._enqueue_refresh(scope_key, "api_export_read_model_unavailable")
        return self.refreshing_payload(scope_key=scope_key)

    def filter_options(self, query: dict[str, list[str]]) -> dict[str, object] | None:
        list_options = getattr(self._repository, "list_input_invoice_usage_filter_options", None)
        scope_key = self.scope_key_from_query(query)
        if not callable(list_options):
            if self._requires_sql_read_model_runtime():
                self._enqueue_refresh(scope_key, "api_filter_options_sql_repository_unavailable")
                return self.refreshing_payload(scope_key=scope_key)
            return None
        try:
            payload = list_options(
                month=query.get("month", [None])[0],
                keyword=query.get("keyword", [None])[0],
                invoice_date_from=query.get("invoice_date_from", [None])[0],
                invoice_date_to=query.get("invoice_date_to", [None])[0],
                filters=query.get("filters", [None])[0],
            )
        except InputInvoiceUsageError:
            raise
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_input_invoice_usage_query", str(exc)) from exc
        if not isinstance(payload, dict):
            self._enqueue_refresh(scope_key, "api_filter_options_miss")
            return self.refreshing_payload(scope_key=scope_key)
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            self._enqueue_refresh(scope_key, "api_filter_options_stale")
            return self.refreshing_payload(scope_key=scope_key)
        stale_reasons = source_version_mismatch_reasons(
            expected=require_expected_source_versions(
                self._expected_source_versions(scope_key=scope_key),
                context="input_invoice_usage_read_model",
            ),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            self._enqueue_refresh(scope_key, "api_filter_options_source_versions_stale")
            return self.refreshing_payload(scope_key=scope_key, stale_reasons=stale_reasons)

        options_by_field = payload.get("options") if isinstance(payload.get("options"), dict) else {}
        fields: list[dict[str, object]] = []
        for config in self._filter_config():
            if not isinstance(config, dict):
                continue
            field = str(config.get("field") or "")
            options = options_by_field.get(field) if isinstance(options_by_field, dict) else []
            fields.append({**config, "options": list(options) if isinstance(options, list) else []})
        return {
            "fields": fields,
            "context": {
                "keyword": query.get("keyword", [""])[0] or "",
                "invoiceDateFrom": query.get("invoice_date_from", [None])[0],
                "invoiceDateTo": query.get("invoice_date_to", [None])[0],
                "month": query.get("month", [None])[0],
                "filters": self._parse_filters(query.get("filters", [None])[0]),
            },
            "read_model_status": "fresh",
            "read_model_scope_key": scope_key,
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
        except InputInvoiceUsageError:
            raise
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
        parsed_filters = self._parse_filters(query.get("filters", [None])[0])
        sort_field, sort_direction = self._parse_sort(
            query.get("sort_field", ["invoice_date"])[0],
            query.get("sort_direction", ["desc"])[0],
        )
        result = dict(payload)
        result["filterConfig"] = self._filter_config()
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

    def rows_by_invoice_ids(self, invoice_ids: list[str]) -> dict[str, object] | None:
        list_rows = getattr(self._repository, "list_input_invoice_usage_rows_by_invoice_ids", None)
        if not callable(list_rows):
            if self._requires_sql_read_model_runtime():
                self._enqueue_refresh("all", "api_invoice_id_lookup_sql_repository_unavailable")
                return self.refreshing_payload(scope_key="all")
            return None
        payload = list_rows(invoice_ids)
        if not isinstance(payload, dict):
            self._enqueue_refresh("all", "api_invoice_id_lookup_miss")
            return self.refreshing_payload(scope_key="all")
        scope_keys = [
            str(scope_key or "all")
            for scope_key in list(payload.get("read_model_scope_keys") or [])
            if str(scope_key or "").strip()
        ] or ["all"]
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            for scope_key in scope_keys:
                self._enqueue_refresh(scope_key, "api_invoice_id_lookup_stale")
            return self.refreshing_payload(scope_key=scope_keys[0])

        source_versions_by_scope = payload.get("source_versions_by_scope") if isinstance(payload.get("source_versions_by_scope"), dict) else {}
        stale_reasons: list[str] = []
        for scope_key in scope_keys:
            actual_versions = source_versions_by_scope.get(scope_key) if isinstance(source_versions_by_scope.get(scope_key), dict) else {}
            scope_stale_reasons = source_version_mismatch_reasons(
                expected=require_expected_source_versions(
                    self._expected_source_versions(scope_key=scope_key),
                    context="input_invoice_usage_read_model",
                ),
                actual=actual_versions,
            )
            if scope_stale_reasons:
                self._enqueue_refresh(scope_key, "api_invoice_id_lookup_source_versions_stale")
                stale_reasons.extend(scope_stale_reasons)
        if stale_reasons:
            return self.refreshing_payload(scope_key=scope_keys[0], stale_reasons=stale_reasons)

        result = dict(payload)
        result["read_model_status"] = "fresh"
        result.pop("refresh_status", None)
        return result

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

    def _parse_filters(self, raw_filters: object) -> dict[str, object]:
        parser = getattr(self._query_service, "_parse_filters", None)
        if callable(parser):
            return parser(raw_filters)
        return {}

    def _parse_sort(self, raw_field: object, raw_direction: object) -> tuple[str, str]:
        parser = getattr(self._query_service, "_parse_sort", None)
        if callable(parser):
            return parser(raw_field, raw_direction)
        field = str(raw_field or "invoice_date").strip() or "invoice_date"
        direction = str(raw_direction or "desc").strip().lower()
        return field, "asc" if direction == "asc" else "desc"

    def _filter_config(self) -> list[dict[str, object]]:
        loader = getattr(self._query_service, "_filter_config", None)
        if callable(loader):
            return loader()
        return []

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
            "readModelStatus": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload
