from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION


SEARCH_INDEX_SCHEMA_VERSION = "2026-05-search-index-v1"


class SearchIndexSourceVersionsProvider:
    def __init__(
        self,
        *,
        bank_auto_tag_rules_version_provider: Callable[[], object],
        oa_attachment_invoice_parser_version_provider: Callable[[], object],
        oa_projection_sync_version_provider: Callable[[], object],
    ) -> None:
        self._bank_auto_tag_rules_version_provider = bank_auto_tag_rules_version_provider
        self._oa_attachment_invoice_parser_version_provider = oa_attachment_invoice_parser_version_provider
        self._oa_projection_sync_version_provider = oa_projection_sync_version_provider

    def expected_source_versions(self) -> dict[str, object]:
        return {
            "search_index_schema_version": SEARCH_INDEX_SCHEMA_VERSION,
            "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
            "bank_auto_tag_rules_version": self._bank_auto_tag_rules_version_provider(),
            "oa_attachment_invoice_parser_version": self._oa_attachment_invoice_parser_version_provider(),
            "oa_projection_sync_version": self._oa_projection_sync_version_provider(),
        }


class SearchQueryFreshnessService:
    def __init__(
        self,
        *,
        read_repository: Any | None,
        source_versions_provider: Callable[[], dict[str, object]],
        enqueue_refresh: Callable[..., bool],
    ) -> None:
        self._read_repository = read_repository
        self._source_versions_provider = source_versions_provider
        self._enqueue_refresh = enqueue_refresh

    def get_payload(
        self,
        *,
        q: str,
        scope: str,
        month: str,
        project_name: str | None,
        status: str | None,
        limit: int,
    ) -> dict[str, object] | None:
        search_index = getattr(self._read_repository, "search_index", None)
        if not callable(search_index):
            return None
        payload = search_index(
            q=q,
            scope=scope,
            month=month,
            project_name=project_name,
            status=status,
            limit=limit,
        )
        scope_key = self.scope_key(month)
        if not isinstance(payload, dict):
            self._enqueue_refresh(scope_key, reason="api_miss")
            return self.empty_payload(
                q=q,
                scope=scope,
                month=month,
                project_name=project_name,
                status=status,
                limit=limit,
                scope_key=scope_key,
            )

        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            self._enqueue_refresh(scope_key, reason="api_stale")
        stale_reasons = source_version_mismatch_reasons(
            expected=require_expected_source_versions(
                self.expected_source_versions(),
                context="search_index_read_model",
            ),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            refresh_status = "stale"
            self._enqueue_refresh(scope_key, reason="api_source_versions_stale")
        result = dict(payload)
        result["read_model_status"] = refresh_status
        result["read_model_scope_key"] = scope_key
        if stale_reasons:
            result["read_model_stale_reasons"] = stale_reasons
        result.pop("refresh_status", None)
        return result

    def expected_source_versions(self) -> dict[str, object]:
        return dict(self._source_versions_provider() or {})

    @staticmethod
    def scope_key(month: str) -> str:
        return month if month != "all" and SEARCH_MONTH_RE.match(month) else "all"

    @staticmethod
    def empty_payload(
        *,
        q: str,
        scope: str,
        month: str,
        project_name: str | None,
        status: str | None,
        limit: int,
        scope_key: str,
    ) -> dict[str, object]:
        return {
            "query": q,
            "filters": {
                "scope": scope,
                "month": month,
                "project_name": project_name or None,
                "status": status,
                "limit": limit,
            },
            "summary": {"total": 0, "oa": 0, "bank": 0, "invoice": 0},
            "oa_results": [],
            "bank_results": [],
            "invoice_results": [],
            "read_model_status": "refreshing",
            "read_model_scope_key": scope_key,
        }
