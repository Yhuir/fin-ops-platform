from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable


@dataclass(frozen=True)
class WorkbenchQueryResult:
    status_code: HTTPStatus
    payload: dict[str, object]


class WorkbenchQueryFacade:
    def __init__(
        self,
        *,
        repository: object | None,
        redis_helper: object | None,
        enqueue_refresh: Callable[..., None],
        scope_key_for_month: Callable[[str | None], str],
        stale_reasons: Callable[..., list[str]],
        emit_status_metric: Callable[..., None],
        missing_read_model_error: Callable[[Exception], bool],
        transient_read_model_error: Callable[[Exception], bool] | None = None,
        refresh_status_with_source_freshness: Callable[..., dict[str, object]] | None = None,
        normalize_refresh_status_payload: Callable[..., dict[str, object]] | None = None,
        groups_redis_version_key: Callable[[str], str] | None = None,
        groups_cache_key_from_version: Callable[..., str | None] | None = None,
        groups_cache_key: Callable[..., str | None] | None = None,
        groups_cache_version_from_key: Callable[[str], str | None] | None = None,
        groups_redis_ttl_seconds: Callable[[], int] | None = None,
        oa_status_provider: Callable[[], object] | None = None,
        serialize_value: Callable[[object], object] | None = None,
    ) -> None:
        self._repository = repository
        self._redis_helper = redis_helper
        self._enqueue_refresh = enqueue_refresh
        self._scope_key_for_month = scope_key_for_month
        self._stale_reasons = stale_reasons
        self._emit_status_metric = emit_status_metric
        self._missing_read_model_error = missing_read_model_error
        self._transient_read_model_error = transient_read_model_error or (lambda _error: False)
        self._refresh_status_with_source_freshness = refresh_status_with_source_freshness
        self._normalize_refresh_status_payload = normalize_refresh_status_payload
        self._groups_redis_version_key = groups_redis_version_key
        self._groups_cache_key_from_version = groups_cache_key_from_version
        self._groups_cache_key = groups_cache_key
        self._groups_cache_version_from_key = groups_cache_version_from_key
        self._groups_redis_ttl_seconds = groups_redis_ttl_seconds or (lambda: 600)
        self._oa_status_provider = oa_status_provider
        self._serialize_value = serialize_value or (lambda value: value)

    def summary(self, month: str | None) -> WorkbenchQueryResult:
        current_month = month or "all"
        scope_key = self._scope_key_for_month(current_month)
        get_summary = getattr(self._repository, "get_workbench_summary", None)
        if not callable(get_summary):
            self._emit_status_metric(
                endpoint="/api/workbench/summary",
                scope_key=scope_key,
                read_model_status="unavailable",
                reason="repository_unavailable",
            )
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "read_model_unavailable",
                    "read_model_status": "unavailable",
                    "scope_key": scope_key,
                    "message": "Workbench SQL summary repository is not configured.",
                },
            )
        try:
            payload = get_summary(scope_key=scope_key)
        except Exception as error:
            if self._missing_read_model_error(error):
                self._emit_status_metric(
                    endpoint="/api/workbench/summary",
                    scope_key=scope_key,
                    read_model_status="unavailable",
                    reason="migration_missing",
                )
                return WorkbenchQueryResult(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "read_model_unavailable",
                        "read_model_status": "unavailable",
                        "scope_key": scope_key,
                        "message": "Workbench SQL groups read model table is not migrated.",
                    },
                )
            raise
        if not isinstance(payload, dict):
            self._enqueue_refresh(scope_key, reason="api_summary_miss")
            self._emit_status_metric(
                endpoint="/api/workbench/summary",
                scope_key=scope_key,
                read_model_status="refreshing",
                reason="api_summary_miss",
            )
            return WorkbenchQueryResult(
                HTTPStatus.ACCEPTED,
                {
                    "month": current_month,
                    "scope_key": scope_key,
                    "summary": {
                        "oa_count": 0,
                        "bank_count": 0,
                        "invoice_count": 0,
                        "paired_count": 0,
                        "open_count": 0,
                        "exception_count": 0,
                    },
                    "read_model_status": "refreshing",
                    "generated_at": None,
                },
            )
        payload = dict(payload)
        stale_reasons = self._stale_reasons(payload.get("source_versions"), scope_key=scope_key)
        if stale_reasons:
            payload["read_model_status"] = "stale"
            payload["read_model_stale_reasons"] = [
                *list(payload.get("read_model_stale_reasons") if isinstance(payload.get("read_model_stale_reasons"), list) else []),
                *stale_reasons,
            ]
            self._enqueue_refresh(scope_key, reason="api_summary_source_versions_stale")
        if "oa_status" not in payload and callable(self._oa_status_provider):
            payload["oa_status"] = self._serialize_value(self._oa_status_provider())
        summary_status = str(payload.get("read_model_status") or "fresh")
        if summary_status != "fresh":
            self._emit_status_metric(
                endpoint="/api/workbench/summary",
                scope_key=scope_key,
                read_model_status=summary_status,
                reason="sql_status",
            )
        return WorkbenchQueryResult(HTTPStatus.OK, payload)

    def groups(
        self,
        month: str | None,
        *,
        zone: str,
        page: str | None = None,
        page_size: str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        search_mode: str | None = None,
        search_by_pane: dict[str, object] | None = None,
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: dict[str, object] | None = None,
        time_filters: dict[str, object] | None = None,
    ) -> WorkbenchQueryResult:
        current_month = month or "all"
        scope_key = self._scope_key_for_month(current_month)
        get_groups_page = getattr(self._repository, "get_workbench_groups_page", None)
        if not callable(get_groups_page):
            self._emit_status_metric(
                endpoint="/api/workbench/groups",
                scope_key=scope_key,
                read_model_status="unavailable",
                reason="repository_unavailable",
            )
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "read_model_unavailable",
                    "read_model_status": "unavailable",
                    "scope_key": scope_key,
                    "message": "Workbench SQL groups repository is not configured.",
                },
            )
        try:
            refresh_status_payload = self._groups_refresh_status_payload(scope_key)
        except Exception as error:
            if self._transient_read_model_error(error):
                return self._read_model_temporarily_unavailable_result(
                    endpoint="/api/workbench/groups",
                    scope_key=scope_key,
                )
            raise
        get_cached = getattr(self._redis_helper, "get_json", None)
        get_text = getattr(self._redis_helper, "get_text", None)
        set_text = getattr(self._redis_helper, "set_text", None)
        version_key = self._groups_redis_version_key(scope_key) if callable(self._groups_redis_version_key) else None
        redis_cache_version = get_text(version_key) if version_key and callable(get_text) else None
        cache_kwargs = {
            "scope_key": scope_key,
            "zone": zone,
            "page": page,
            "page_size": page_size,
            "status": status,
            "source_kind": source_kind,
            "search": search,
            "search_mode": search_mode,
            "search_by_pane": search_by_pane,
            "sort": sort,
            "detail_level": detail_level,
            "column_filters": column_filters,
            "time_filters": time_filters,
        }
        cache_key = (
            self._groups_cache_key_from_version(cache_version=redis_cache_version, **cache_kwargs)
            if callable(self._groups_cache_key_from_version)
            else None
        )
        can_use_groups_redis_cache = (
            refresh_status_payload is None
            or str(refresh_status_payload.get("read_model_status") or "fresh") == "fresh"
        )
        cached_result = self._cached_groups_payload(
            cache_key,
            get_cached=get_cached,
            can_use_cache=can_use_groups_redis_cache,
            scope_key=scope_key,
        )
        if cached_result is not None:
            return cached_result
        if cache_key is None and callable(self._groups_cache_key):
            try:
                cache_key = self._groups_cache_key(repository=self._repository, **cache_kwargs)
            except Exception as error:
                if self._transient_read_model_error(error):
                    return self._read_model_temporarily_unavailable_result(
                        endpoint="/api/workbench/groups",
                        scope_key=scope_key,
                    )
                raise
        if cache_key and can_use_groups_redis_cache and callable(set_text) and callable(self._groups_cache_version_from_key):
            parsed_version = self._groups_cache_version_from_key(cache_key)
            if parsed_version and version_key:
                set_text(version_key, parsed_version, ttl_seconds=self._groups_redis_ttl_seconds())
        cached_result = self._cached_groups_payload(
            cache_key,
            get_cached=get_cached,
            can_use_cache=can_use_groups_redis_cache,
            scope_key=scope_key,
        )
        if cached_result is not None:
            return cached_result
        try:
            payload = get_groups_page(**cache_kwargs)
        except Exception as error:
            if self._missing_read_model_error(error):
                self._emit_status_metric(
                    endpoint="/api/workbench/groups",
                    scope_key=scope_key,
                    read_model_status="unavailable",
                    reason="migration_missing",
                )
                return WorkbenchQueryResult(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "read_model_unavailable",
                        "read_model_status": "unavailable",
                        "scope_key": scope_key,
                        "message": "Workbench SQL groups read model table is not migrated.",
                    },
                )
            if self._transient_read_model_error(error):
                return self._read_model_temporarily_unavailable_result(
                    endpoint="/api/workbench/groups",
                    scope_key=scope_key,
                )
            raise
        if not isinstance(payload, dict):
            self._enqueue_refresh(scope_key, reason="api_groups_miss")
            self._emit_status_metric(
                endpoint="/api/workbench/groups",
                scope_key=scope_key,
                read_model_status="refreshing",
                reason="api_groups_miss",
            )
            return WorkbenchQueryResult(
                HTTPStatus.ACCEPTED,
                {
                    "month": current_month,
                    "scope_key": scope_key,
                    "zone": zone,
                    "page": 1,
                    "page_size": 50,
                    "total": 0,
                    "has_more": False,
                    "groups": [],
                    "read_model_status": "refreshing",
                },
            )
        payload = dict(payload)
        payload["read_model_scope_key"] = scope_key
        stale_reasons = self._stale_reasons(payload.get("source_versions"), scope_key=scope_key)
        if stale_reasons:
            payload["read_model_status"] = "stale"
            payload["read_model_stale_reasons"] = [
                *list(payload.get("read_model_stale_reasons") if isinstance(payload.get("read_model_stale_reasons"), list) else []),
                *stale_reasons,
            ]
        groups_status = str(payload.get("read_model_status") or "fresh")
        if groups_status != "fresh":
            self._enqueue_refresh(scope_key, reason="api_groups_stale")
            self._emit_status_metric(
                endpoint="/api/workbench/groups",
                scope_key=scope_key,
                read_model_status=groups_status,
                reason="sql_status",
            )
        set_cached = getattr(self._redis_helper, "set_json", None)
        if cache_key and can_use_groups_redis_cache and callable(set_cached) and payload.get("read_model_status") == "fresh":
            set_cached(cache_key, {"payload": payload}, ttl_seconds=self._groups_redis_ttl_seconds())
        return WorkbenchQueryResult(HTTPStatus.OK, payload)

    def group_detail(self, month: str | None, *, zone: str, group_id: str) -> WorkbenchQueryResult:
        current_month = month or "all"
        scope_key = self._scope_key_for_month(current_month)
        get_group_detail = getattr(self._repository, "get_workbench_group_detail", None)
        if not callable(get_group_detail):
            self._emit_status_metric(
                endpoint="/api/workbench/groups/detail",
                scope_key=scope_key,
                read_model_status="unavailable",
                reason="repository_unavailable",
            )
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "read_model_unavailable",
                    "read_model_status": "unavailable",
                    "scope_key": scope_key,
                    "message": "Workbench SQL group detail repository is not configured.",
                },
            )
        try:
            group = get_group_detail(scope_key=scope_key, zone=zone, group_id=group_id)
        except Exception as error:
            if self._missing_read_model_error(error):
                self._emit_status_metric(
                    endpoint="/api/workbench/groups/detail",
                    scope_key=scope_key,
                    read_model_status="unavailable",
                    reason="migration_missing",
                )
                return WorkbenchQueryResult(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "read_model_unavailable",
                        "read_model_status": "unavailable",
                        "scope_key": scope_key,
                        "message": "Workbench SQL groups read model table is not migrated.",
                    },
                )
            raise
        if not isinstance(group, dict):
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "workbench_group_not_found",
                    "scope_key": scope_key,
                    "zone": zone,
                    "group_id": group_id,
                },
            )
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {
                "month": current_month,
                "scope_key": scope_key,
                "zone": zone,
                "group_id": group_id,
                "group": group,
                "read_model_status": "fresh",
            },
        )

    def row_detail(self, month: str | None, *, row_id: str) -> WorkbenchQueryResult:
        current_month = month or "all"
        scope_key = self._scope_key_for_month(current_month)
        normalized_row_id = str(row_id or "").strip()
        get_row_detail = getattr(self._repository, "get_workbench_row_detail", None)
        if not callable(get_row_detail):
            self._emit_status_metric(
                endpoint="/api/workbench/rows/{row_id}",
                scope_key=scope_key,
                read_model_status="unavailable",
                reason="repository_unavailable",
            )
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "read_model_unavailable",
                    "read_model_status": "unavailable",
                    "scope_key": scope_key,
                    "message": "Workbench SQL row detail repository is not configured.",
                },
            )
        if not normalized_row_id:
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "scope_key": scope_key, "row_id": normalized_row_id},
            )
        try:
            payload = get_row_detail(scope_key=scope_key, row_id=normalized_row_id)
        except Exception as error:
            if self._missing_read_model_error(error):
                self._emit_status_metric(
                    endpoint="/api/workbench/rows/{row_id}",
                    scope_key=scope_key,
                    read_model_status="unavailable",
                    reason="migration_missing",
                )
                return WorkbenchQueryResult(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "read_model_unavailable",
                        "read_model_status": "unavailable",
                        "scope_key": scope_key,
                        "message": "Workbench SQL row detail read model table is not migrated.",
                    },
                )
            if self._transient_read_model_error(error):
                return self._read_model_temporarily_unavailable_result(
                    endpoint="/api/workbench/rows/{row_id}",
                    scope_key=scope_key,
                )
            raise
        if not isinstance(payload, dict) or not isinstance(payload.get("row"), dict):
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "scope_key": scope_key, "row_id": normalized_row_id},
            )
        result = dict(payload)
        stale_reasons = self._stale_reasons(result.get("source_versions"), scope_key=str(result.get("scope_key") or scope_key))
        if stale_reasons:
            result["read_model_status"] = "stale"
            result["read_model_stale_reasons"] = [
                *list(result.get("read_model_stale_reasons") if isinstance(result.get("read_model_stale_reasons"), list) else []),
                *stale_reasons,
            ]
            self._enqueue_refresh(str(result.get("scope_key") or scope_key), reason="api_row_detail_source_versions_stale")
            self._emit_status_metric(
                endpoint="/api/workbench/rows/{row_id}",
                scope_key=str(result.get("scope_key") or scope_key),
                read_model_status="stale",
                reason="sql_status",
            )
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "scope_key": scope_key, "row_id": normalized_row_id},
            )
        result.setdefault("scope_key", scope_key)
        result.setdefault("read_model_status", "fresh")
        return WorkbenchQueryResult(HTTPStatus.OK, result)

    def refresh_status(self, month: str | None) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        get_refresh_status = getattr(self._repository, "get_workbench_refresh_status", None)
        if not callable(get_refresh_status):
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "read_model_unavailable",
                    "read_model_status": "unavailable",
                    "scope_key": scope_key,
                    "message": "Workbench SQL refresh status repository is not configured.",
                },
            )
        try:
            payload = get_refresh_status(scope_key=scope_key)
        except Exception as error:
            if self._transient_read_model_error(error):
                return self._read_model_temporarily_unavailable_result(
                    endpoint="/api/workbench/refresh-status",
                    scope_key=scope_key,
                )
            raise
        if isinstance(payload, dict) and callable(self._refresh_status_with_source_freshness):
            payload = self._refresh_status_with_source_freshness(payload, scope_key=scope_key)
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            self._normalize_refresh_status(payload if isinstance(payload, dict) else {}, scope_key=scope_key, payload_is_dict=isinstance(payload, dict)),
        )

    def _groups_refresh_status_payload(self, scope_key: str) -> dict[str, object] | None:
        get_refresh_status = getattr(self._repository, "get_workbench_groups_freshness_status", None)
        if not callable(get_refresh_status):
            get_refresh_status = getattr(self._repository, "get_workbench_refresh_status", None)
        if not callable(get_refresh_status):
            return None
        raw_refresh_status = get_refresh_status(scope_key=scope_key)
        if not isinstance(raw_refresh_status, dict):
            return None
        refresh_status_payload = (
            self._refresh_status_with_source_freshness(raw_refresh_status, scope_key=scope_key)
            if callable(self._refresh_status_with_source_freshness)
            else raw_refresh_status
        )
        if str(refresh_status_payload.get("read_model_status") or "fresh") != "fresh":
            self._enqueue_refresh(scope_key, reason="api_groups_source_versions_stale")
        return refresh_status_payload

    def _read_model_temporarily_unavailable_result(
        self,
        *,
        endpoint: str,
        scope_key: str,
    ) -> WorkbenchQueryResult:
        self._emit_status_metric(
            endpoint=endpoint,
            scope_key=scope_key,
            read_model_status="refreshing",
            reason="query_timeout",
        )
        return WorkbenchQueryResult(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "read_model_temporarily_unavailable",
                "read_model_status": "refreshing",
                "retryable": True,
                "scope_key": scope_key,
                "message": "Workbench SQL read model query timed out; retry after refresh.",
            },
        )

    def _cached_groups_payload(
        self,
        cache_key: str | None,
        *,
        get_cached: object,
        can_use_cache: bool,
        scope_key: str,
    ) -> WorkbenchQueryResult | None:
        if not cache_key or not callable(get_cached) or not can_use_cache:
            return None
        cached = get_cached(cache_key)
        if not isinstance(cached, dict):
            return None
        payload = dict(cached.get("payload") if isinstance(cached.get("payload"), dict) else cached)
        payload["read_model_status"] = "fresh"
        payload["read_model_scope_key"] = scope_key
        return WorkbenchQueryResult(HTTPStatus.OK, payload)

    def _normalize_refresh_status(
        self,
        payload: dict[str, object],
        *,
        scope_key: str,
        payload_is_dict: bool,
    ) -> dict[str, object]:
        if callable(self._normalize_refresh_status_payload):
            return self._normalize_refresh_status_payload(
                payload,
                scope_key=scope_key,
                fallback_status="unavailable" if not payload_is_dict else "fresh",
            )
        result = dict(payload)
        result.setdefault("scope_key", scope_key)
        result.setdefault("read_model_status", "fresh" if payload_is_dict else "unavailable")
        return result
