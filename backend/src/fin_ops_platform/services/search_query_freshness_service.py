from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE


class SearchQueryFreshnessService:
    def __init__(
        self,
        *,
        read_repository: Any | None,
        enqueue_refresh: Callable[..., bool],
    ) -> None:
        self._read_repository = read_repository
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
        result = dict(payload)
        result["read_model_status"] = refresh_status
        result["read_model_scope_key"] = scope_key
        result.pop("refresh_status", None)
        return result

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
