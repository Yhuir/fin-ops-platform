from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.output_invoice_collection_read_model_detail_service import (
    OutputInvoiceCollectionReadModelDetailService,
)
from fin_ops_platform.services.invoice_usage_collection_dependency_gate import (
    InvoiceUsageCollectionDependencyGate,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionError
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)


class OutputInvoiceCollectionReadModelFreshGateService:
    def __init__(
        self,
        *,
        repository: Any | None,
        query_service: Any | None,
        requires_sql_read_model_runtime: Callable[[], bool],
        enqueue_refresh: Callable[[str, str], bool],
        expected_source_versions: Callable[..., dict[str, object]],
        workbench_relation_reader: Any | None = None,
    ) -> None:
        self._repository = repository
        self._query_service = query_service
        self._requires_sql_read_model_runtime = requires_sql_read_model_runtime
        self._enqueue_refresh = enqueue_refresh
        self._expected_source_versions = expected_source_versions
        self._relation_dependency_gate = InvoiceUsageCollectionDependencyGate(
            scope_state_loader=getattr(
                repository,
                "output_invoice_collection_scope_source_versions",
                None,
            ),
            relation_reader=workbench_relation_reader,
            expected_source_versions=expected_source_versions,
            requires_sql_runtime=requires_sql_read_model_runtime,
            context="output_invoice_collection_read_model",
        )

    def all_rows(self, query: dict[str, list[str]]) -> dict[str, object] | None:
        page_size = 200
        first_query = {key: list(values) for key, values in query.items()}
        first_query["page"] = ["1"]
        first_query["page_size"] = [str(page_size)]
        first_payload = self.rows(first_query, include_statistics=False)
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
            page_payload = self.rows(page_query, include_statistics=False)
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

    def rows(
        self,
        query: dict[str, list[str]],
        *,
        include_statistics: bool = True,
    ) -> dict[str, object] | None:
        list_rows = getattr(self._repository, "list_output_invoice_collection_rows", None)
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
            reason="output_invoice_collection_rows",
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
        except ValueError as exc:
            raise OutputInvoiceCollectionError("invalid_output_invoice_collection_query", str(exc)) from exc
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
                context="output_invoice_collection_read_model",
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
        result["readModelStatus"] = "fresh"
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
                context="output_invoice_collection_statistics",
            ),
            actual=actual_versions,
        )
        if status == "fresh" and isinstance(payload.get("statistics"), dict) and not stale_reasons:
            return
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
        if not callable(getattr(self._repository, "get_output_invoice_collection_row_by_row_id", None)):
            if self._requires_sql_read_model_runtime():
                if self._relation_dependency_gate.is_concrete_scope_key(
                    requested_scope_key
                ):
                    self._enqueue_refresh(
                        requested_scope_key,
                        "api_detail_sql_repository_unavailable",
                    )
                return OutputInvoiceCollectionReadModelDetailService.refreshing_payload(
                    kind=query.get("kind", [""])[0],
                    scope_key=requested_scope_key,
                )
            return None
        service = OutputInvoiceCollectionReadModelDetailService(
            repository=self._repository,
            enqueue_refresh=self._enqueue_refresh,
            source_versions_provider=self._expected_source_versions,
        )
        return service.relation_details(
            row_id,
            kind=query.get("kind", [""])[0],
            requested_scope_key=requested_scope_key,
        )

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
    def payload_requires_schema_refresh(payload: dict[str, object]) -> bool:
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                return True
            if not isinstance(row.get("invoice"), dict):
                return True
            if not isinstance(row.get("collectionStatus"), dict):
                return True
            if not isinstance(row.get("oa"), dict):
                return True
            if not isinstance(row.get("bankTransactions"), dict):
                return True
            if not isinstance(row.get("invoiceRelations"), dict):
                return True
            if not isinstance(row.get("redInvoiceRelation"), dict):
                return True
            if not isinstance(row.get("receipt"), dict):
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
