from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.input_invoice_usage_read_model_detail_service import (
    InputInvoiceUsageReadModelDetailService,
)
from fin_ops_platform.services.input_invoice_usage_query_contract import (
    InputInvoiceUsageQueryContractError,
    input_invoice_usage_filter_config,
    parse_input_invoice_usage_filters,
    parse_input_invoice_usage_sort,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageError
from fin_ops_platform.services.invoice_usage_collection_dependency_gate import (
    InvoiceUsageCollectionDependencyGate,
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
        requires_sql_read_model_runtime: Callable[[], bool],
        enqueue_refresh: Callable[[str, str], bool],
        expected_source_versions: Callable[..., dict[str, object]],
        workbench_relation_reader: Any | None = None,
        statistics_overlay: Callable[[], dict[str, object]] | None = None,
    ) -> None:
        self._repository = repository
        self._requires_sql_read_model_runtime = requires_sql_read_model_runtime
        self._enqueue_refresh = enqueue_refresh
        self._expected_source_versions = expected_source_versions
        self._statistics_overlay = statistics_overlay
        self._relation_dependency_gate = InvoiceUsageCollectionDependencyGate(
            scope_state_loader=getattr(
                repository,
                "input_invoice_usage_scope_source_versions",
                None,
            ),
            relation_reader=workbench_relation_reader,
            relation_source_versions_loader=getattr(
                repository,
                "input_invoice_usage_relation_source_versions",
                None,
            ),
            expected_source_versions=expected_source_versions,
            requires_sql_runtime=requires_sql_read_model_runtime,
            context="input_invoice_usage_read_model",
        )

    def export_page(self, **kwargs: object) -> dict[str, object] | None:
        include_statistics = bool(kwargs.pop("include_statistics", True))
        query = self.export_query_from_kwargs(kwargs)
        sql_payload = self.rows(query, include_statistics=include_statistics)
        if sql_payload is not None:
            return sql_payload
        scope_key = self.scope_key_from_query(query)
        refresh_scope_keys = self._enqueue_scope_refreshes(
            scope_key,
            reason="api_export_read_model_unavailable",
        )
        return self.refreshing_payload(
            scope_key=scope_key,
            refresh_scope_keys=refresh_scope_keys,
        )

    def filter_options(self, query: dict[str, list[str]]) -> dict[str, object] | None:
        list_options = getattr(self._repository, "list_input_invoice_usage_filter_options", None)
        scope_key = self.scope_key_from_query(query)
        if not callable(list_options):
            if self._requires_sql_read_model_runtime():
                refresh_scope_keys = self._enqueue_scope_refreshes(
                    scope_key,
                    reason="api_filter_options_sql_repository_unavailable",
                )
                return self.refreshing_payload(
                    scope_key=scope_key,
                    refresh_scope_keys=refresh_scope_keys,
                )
            return None
        dependency_status = self._relation_dependency_gate.resolve(
            scope_key,
            reason="input_invoice_usage_filter_options",
        )
        if dependency_status["status"] != "fresh":
            refresh_scope_keys = self._relation_dependency_gate.concrete_scope_keys(
                list(dependency_status.get("refresh_scope_keys") or [])
            )
            if scope_key != "all":
                refresh_scope_keys = [
                    candidate
                    for candidate in refresh_scope_keys
                    if candidate == scope_key
                ]
            for refresh_scope_key in refresh_scope_keys:
                self._enqueue_refresh(
                    refresh_scope_key,
                    "api_filter_options_relation_dependency_stale",
                )
            return self.refreshing_payload(
                scope_key=scope_key,
                stale_reasons=list(dependency_status.get("stale_reasons") or []),
                refresh_scope_keys=refresh_scope_keys,
            )
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
            refresh_scope_keys = self._enqueue_scope_refreshes(
                scope_key,
                reason="api_filter_options_miss",
                candidate_scope_keys=list(dependency_status.get("scope_keys") or []),
            )
            return self.refreshing_payload(
                scope_key=scope_key,
                refresh_scope_keys=refresh_scope_keys,
            )
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            refresh_scope_keys = self._enqueue_scope_refreshes(
                scope_key,
                reason="api_filter_options_stale",
                candidate_scope_keys=list(dependency_status.get("scope_keys") or []),
            )
            return self.refreshing_payload(
                scope_key=scope_key,
                refresh_scope_keys=refresh_scope_keys,
            )
        stale_reasons = source_version_mismatch_reasons(
            expected=require_expected_source_versions(
                self._expected_source_versions(scope_key=scope_key),
                context="input_invoice_usage_read_model",
            ),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            refresh_scope_keys = self._enqueue_scope_refreshes(
                scope_key,
                reason="api_filter_options_source_versions_stale",
                candidate_scope_keys=list(dependency_status.get("scope_keys") or []),
            )
            return self.refreshing_payload(
                scope_key=scope_key,
                stale_reasons=stale_reasons,
                refresh_scope_keys=refresh_scope_keys,
            )

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

    def rows(
        self,
        query: dict[str, list[str]],
        *,
        include_statistics: bool = True,
    ) -> dict[str, object] | None:
        list_rows = getattr(self._repository, "list_input_invoice_usage_rows", None)
        scope_key = self.scope_key_from_query(query)
        if not callable(list_rows):
            if self._requires_sql_read_model_runtime():
                refresh_scope_keys = self._enqueue_scope_refreshes(
                    scope_key,
                    reason="api_sql_repository_unavailable",
                )
                return self.refreshing_payload(
                    scope_key=scope_key,
                    refresh_scope_keys=refresh_scope_keys,
                )
            return None
        dependency_status = self._relation_dependency_gate.resolve(
            "all" if include_statistics else scope_key,
            reason="input_invoice_usage_rows",
        )
        blocking_scope_keys = list(dependency_status.get("blocking_scope_keys") or [])
        page_blocking_scope_keys = (
            blocking_scope_keys
            if scope_key == "all"
            else [blocking_scope_key for blocking_scope_key in blocking_scope_keys if blocking_scope_key == scope_key]
        )
        dependency_refresh_scope_keys = self._relation_dependency_gate.concrete_scope_keys(
            list(dependency_status.get("refresh_scope_keys") or [])
        )
        page_dependency_refresh_scope_keys = (
            dependency_refresh_scope_keys
            if scope_key == "all"
            else [
                refresh_scope_key
                for refresh_scope_key in dependency_refresh_scope_keys
                if refresh_scope_key == scope_key
            ]
        )
        dependency_unresolved = (
            str(dependency_status.get("status") or "unavailable") != "fresh"
            and not blocking_scope_keys
        )
        if page_blocking_scope_keys or dependency_unresolved:
            refresh_scope_keys = page_dependency_refresh_scope_keys
            for refresh_scope_key in refresh_scope_keys:
                self._enqueue_refresh(
                    refresh_scope_key,
                    "api_relation_dependency_stale",
                )
            return self.refreshing_payload(
                scope_key=scope_key,
                stale_reasons=list(dependency_status.get("stale_reasons") or []),
                refresh_scope_keys=refresh_scope_keys,
            )
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
                include_statistics=include_statistics,
            )
        except InputInvoiceUsageError:
            raise
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_input_invoice_usage_query", str(exc)) from exc
        if not isinstance(payload, dict):
            refresh_scope_keys = self._enqueue_scope_refreshes(
                scope_key,
                reason="api_miss",
                candidate_scope_keys=list(dependency_status.get("scope_keys") or []),
            )
            return self.refreshing_payload(
                scope_key=scope_key,
                refresh_scope_keys=refresh_scope_keys,
            )
        if self.payload_requires_schema_refresh(payload):
            refresh_scope_keys = self._enqueue_scope_refreshes(
                scope_key,
                reason="api_schema_stale",
                candidate_scope_keys=list(dependency_status.get("scope_keys") or []),
            )
            return self.refreshing_payload(
                scope_key=scope_key,
                refresh_scope_keys=refresh_scope_keys,
            )
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            refresh_scope_keys = self._enqueue_scope_refreshes(
                scope_key,
                reason="api_stale",
                candidate_scope_keys=list(dependency_status.get("scope_keys") or []),
            )
            return self.refreshing_payload(
                scope_key=scope_key,
                refresh_scope_keys=refresh_scope_keys,
            )
        stale_reasons = source_version_mismatch_reasons(
            expected=require_expected_source_versions(
                self._expected_source_versions(scope_key=scope_key),
                context="input_invoice_usage_read_model",
            ),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            refresh_scope_keys = self._enqueue_scope_refreshes(
                scope_key,
                reason="api_source_versions_stale",
                candidate_scope_keys=list(dependency_status.get("scope_keys") or []),
            )
            return self.refreshing_payload(
                scope_key=scope_key,
                stale_reasons=stale_reasons,
                refresh_scope_keys=refresh_scope_keys,
            )
        parsed_filters = self._parse_filters(query.get("filters", [None])[0])
        sort_field, sort_direction = self._parse_sort(
            query.get("sort_field", ["invoice_date"])[0],
            query.get("sort_direction", ["desc"])[0],
        )
        result = dict(payload)
        if include_statistics:
            self._gate_statistics(
                result,
                dependency_blocking_scope_keys=blocking_scope_keys,
                refresh_scope_keys=(
                    dependency_refresh_scope_keys
                    if blocking_scope_keys
                    else list(dependency_status.get("scope_keys") or [])
                ),
            )
        result["filterConfig"] = self._filter_config()
        result["appliedFilters"] = {"filters": parsed_filters}
        result["sort"] = {"field": sort_field, "direction": sort_direction}
        result["read_model_status"] = "fresh"
        result["read_model_scope_key"] = scope_key
        result.pop("refresh_status", None)
        return result

    def _gate_statistics(
        self,
        payload: dict[str, object],
        *,
        dependency_blocking_scope_keys: list[str],
        refresh_scope_keys: list[str],
    ) -> None:
        if dependency_blocking_scope_keys:
            payload["statistics"] = None
            payload["statistics_status"] = "refreshing"
            for scope_key in self._relation_dependency_gate.concrete_scope_keys(
                refresh_scope_keys
            ):
                self._enqueue_refresh(
                    scope_key,
                    "api_statistics_relation_dependency_stale",
                )
            return
        status = str(payload.get("statistics_status") or "stale")
        actual_versions = (
            payload.get("statistics_source_versions")
            if isinstance(payload.get("statistics_source_versions"), dict)
            else {}
        )
        stale_reasons = source_version_mismatch_reasons(
            expected=require_expected_source_versions(
                self._expected_source_versions(scope_key="all"),
                context="input_invoice_usage_statistics",
            ),
            actual=actual_versions,
        )
        if status == "fresh" and isinstance(payload.get("statistics"), dict) and not stale_reasons:
            if callable(self._statistics_overlay):
                overlay = self._statistics_overlay()
                batch_count = (
                    overlay.get("oa_reverse_batch_count")
                    if isinstance(overlay, dict)
                    else None
                )
                if (
                    isinstance(batch_count, int)
                    and not isinstance(batch_count, bool)
                    and batch_count >= 0
                ):
                    payload["statistics"] = {
                        **dict(payload["statistics"]),
                        "oa_reverse_batch_count": batch_count,
                    }
                    return
            if not self._requires_sql_read_model_runtime():
                return
            stale_reasons = ["input_invoice_usage_statistics_overlay_unavailable"]
        payload["statistics"] = None
        payload["statistics_status"] = "refreshing"
        reason = (
            "api_statistics_source_versions_stale"
            if stale_reasons
            else f"api_statistics_{status}"
        )
        for scope_key in self._relation_dependency_gate.concrete_scope_keys(
            refresh_scope_keys
        ):
            self._enqueue_refresh(scope_key, reason)

    def relation_details(self, row_id: str, query: dict[str, list[str]]) -> dict[str, object] | None:
        requested_scope_key = self.scope_key_from_query(query)
        if not callable(getattr(self._repository, "get_input_invoice_usage_row_by_row_id", None)):
            if self._requires_sql_read_model_runtime():
                if self._relation_dependency_gate.is_concrete_scope_key(
                    requested_scope_key
                ):
                    self._enqueue_refresh(
                        requested_scope_key,
                        "api_detail_sql_repository_unavailable",
                    )
                return InputInvoiceUsageReadModelDetailService.refreshing_payload(
                    kind=query.get("kind", [""])[0],
                    scope_key=requested_scope_key,
                )
            return None
        service = InputInvoiceUsageReadModelDetailService(
            repository=self._repository,
            enqueue_refresh=self._enqueue_refresh,
            source_versions_provider=self._expected_source_versions,
        )
        return service.relation_details(
            row_id,
            kind=query.get("kind", [""])[0],
            requested_scope_key=requested_scope_key,
        )

    def rows_by_invoice_ids(self, invoice_ids: list[str]) -> dict[str, object] | None:
        list_rows = getattr(self._repository, "list_input_invoice_usage_rows_by_invoice_ids", None)
        if not callable(list_rows):
            if self._requires_sql_read_model_runtime():
                return self.refreshing_payload(scope_key="all")
            return None
        payload = list_rows(invoice_ids)
        if not isinstance(payload, dict):
            return self.refreshing_payload(scope_key="all")
        scope_keys = self._relation_dependency_gate.concrete_scope_keys(
            [
                str(scope_key or "")
            for scope_key in list(payload.get("read_model_scope_keys") or [])
            if str(scope_key or "").strip()
            ]
        )
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            for scope_key in scope_keys:
                self._enqueue_refresh(scope_key, "api_invoice_id_lookup_stale")
            return self.refreshing_payload(
                scope_key=scope_keys[0] if scope_keys else "all"
            )

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
            return self.refreshing_payload(
                scope_key=scope_keys[0] if scope_keys else "all",
                stale_reasons=stale_reasons,
            )

        result = dict(payload)
        result["read_model_status"] = "fresh"
        result.pop("refresh_status", None)
        return result

    def _enqueue_scope_refreshes(
        self,
        scope_key: str,
        *,
        reason: str,
        candidate_scope_keys: list[object] | None = None,
    ) -> list[str]:
        refresh_scope_keys = (
            [scope_key]
            if self._relation_dependency_gate.is_concrete_scope_key(scope_key)
            else self._relation_dependency_gate.concrete_scope_keys(
                list(candidate_scope_keys or [])
            )
        )
        for refresh_scope_key in refresh_scope_keys:
            self._enqueue_refresh(refresh_scope_key, reason)
        return refresh_scope_keys

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

    def _parse_filters(self, raw_filters: object) -> list[dict[str, object]]:
        try:
            return parse_input_invoice_usage_filters(raw_filters if isinstance(raw_filters, (str, list)) else None)
        except InputInvoiceUsageQueryContractError as exc:
            raise InputInvoiceUsageError(exc.error_code, str(exc), details=exc.details) from exc

    def _parse_sort(self, raw_field: object, raw_direction: object) -> tuple[str, str]:
        try:
            return parse_input_invoice_usage_sort(raw_field, raw_direction)
        except InputInvoiceUsageQueryContractError as exc:
            raise InputInvoiceUsageError(exc.error_code, str(exc), details=exc.details) from exc

    def _filter_config(self) -> list[dict[str, object]]:
        return input_invoice_usage_filter_config()

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
        refresh_scope_keys: list[str] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "rows": [],
            "pagination": {"page": 1, "pageSize": 50, "total": 0},
            "summary": {},
            "statistics": None,
            "statistics_status": "refreshing",
            "filterConfig": [],
            "read_model_status": "refreshing",
            "readModelStatus": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        if refresh_scope_keys:
            payload["read_model_refresh_scope_keys"] = list(refresh_scope_keys)
        return payload
