from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable

from fin_ops_platform.services.workbench_read_model_version import WorkbenchReadModelVersionConflictError


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
        initial_cache_key_from_version: Callable[..., str | None] | None = None,
        is_default_initial_query: Callable[..., bool] | None = None,
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
        self._initial_cache_key_from_version = initial_cache_key_from_version
        self._is_default_initial_query = is_default_initial_query
        self._oa_status_provider = oa_status_provider
        self._serialize_value = serialize_value or (lambda value: value)

    def initial_page(
        self,
        month: str | None,
        *,
        paired_query: dict[str, object] | None = None,
        unpaired_query: dict[str, object] | None = None,
    ) -> WorkbenchQueryResult:
        current_month = month or "all"
        scope_key = self._scope_key_for_month(current_month)
        get_initial_page = getattr(self._repository, "get_workbench_initial_page", None)
        if not callable(get_initial_page):
            self._emit_status_metric(
                endpoint="/api/workbench",
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
                    "message": "Workbench SQL initial page repository is not configured.",
                },
            )
        cacheable_query = bool(
            callable(self._is_default_initial_query)
            and self._is_default_initial_query(paired_query, unpaired_query)
        )
        refresh_status_payload: dict[str, object] | None = None
        if cacheable_query:
            try:
                refresh_status_payload = self._groups_refresh_status_payload(scope_key)
            except Exception as error:
                if not self._transient_read_model_error(error):
                    raise
        refresh_status = (
            str(refresh_status_payload.get("read_model_status") or "fresh")
            if isinstance(refresh_status_payload, dict)
            else ""
        )
        cache_version = (
            str(
                refresh_status_payload.get("read_model_version")
                or refresh_status_payload.get("active_generation_id")
                or ""
            ).strip()
            if isinstance(refresh_status_payload, dict)
            else ""
        )
        cache_key = (
            self._initial_cache_key_from_version(cache_version=cache_version, scope_key=scope_key)
            if cacheable_query and cache_version and callable(self._initial_cache_key_from_version)
            else None
        )
        payload: object = None
        loaded_from_cache = False
        if cache_key and refresh_status in {"fresh", "refreshing"}:
            get_cached = getattr(self._redis_helper, "get_json", None)
            if callable(get_cached):
                try:
                    cached = get_cached(cache_key)
                except Exception:
                    cached = None
                cached_payload = cached.get("payload") if isinstance(cached, dict) else None
                cached_version = (
                    str(cached_payload.get("read_model_version") or "").strip()
                    if isinstance(cached_payload, dict)
                    else ""
                )
                if isinstance(cached_payload, dict) and cached_version == cache_version:
                    payload = dict(cached_payload)
                    loaded_from_cache = True
        try:
            if not loaded_from_cache:
                payload = get_initial_page(
                    scope_key=scope_key,
                    paired_query=paired_query,
                    unpaired_query=unpaired_query,
                )
        except Exception as error:
            if self._missing_read_model_error(error):
                self._emit_status_metric(
                    endpoint="/api/workbench",
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
                        "message": "Workbench SQL read model tables are not migrated.",
                    },
                )
            if self._transient_read_model_error(error):
                return self._read_model_temporarily_unavailable_result(
                    endpoint="/api/workbench",
                    scope_key=scope_key,
                )
            raise
        if not isinstance(payload, dict):
            self._enqueue_refresh(scope_key, reason="api_initial_page_miss")
            self._emit_status_metric(
                endpoint="/api/workbench",
                scope_key=scope_key,
                read_model_status="refreshing",
                reason="api_initial_page_miss",
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
                        "unpaired_count": 0,
                        "exception_count": 0,
                    },
                    "paired": {"groups": [], "total": 0, "has_more": False},
                    "unpaired": {"groups": [], "total": 0, "has_more": False},
                    "read_model_status": "refreshing",
                    "generated_at": None,
                },
            )
        payload = dict(payload)
        payload["read_model_scope_key"] = scope_key
        payload_version = str(payload.get("read_model_version") or "").strip()
        if cacheable_query and cache_version and payload_version != cache_version:
            self._enqueue_refresh(scope_key, reason="api_initial_page_version_drift")
            self._emit_status_metric(
                endpoint="/api/workbench",
                scope_key=scope_key,
                read_model_status="refreshing",
                reason="api_initial_page_version_drift",
            )
            return WorkbenchQueryResult(
                HTTPStatus.ACCEPTED,
                {
                    "error": "workbench_initial_page_version_drift",
                    "month": current_month,
                    "scope_key": scope_key,
                    "read_model_scope_key": scope_key,
                    "read_model_status": "refreshing",
                    "expected_read_model_version": cache_version,
                    "read_model_version": payload_version or None,
                    "summary": {
                        "oa_count": 0,
                        "bank_count": 0,
                        "invoice_count": 0,
                        "paired_count": 0,
                        "unpaired_count": 0,
                        "exception_count": 0,
                    },
                    "paired": {"groups": [], "total": 0, "has_more": False},
                    "unpaired": {"groups": [], "total": 0, "has_more": False},
                },
            )
        if refresh_status_payload and cache_version == payload_version and refresh_status in {"refreshing", "stale"}:
            payload["read_model_status"] = refresh_status
            context_stale_reasons = refresh_status_payload.get("read_model_stale_reasons")
            if isinstance(context_stale_reasons, list) and context_stale_reasons:
                payload["read_model_stale_reasons"] = list(context_stale_reasons)
        stale_reasons = self._stale_reasons(payload.get("source_versions"), scope_key=scope_key)
        if stale_reasons:
            payload["read_model_status"] = "stale"
            payload["read_model_stale_reasons"] = [
                *list(
                    payload.get("read_model_stale_reasons")
                    if isinstance(payload.get("read_model_stale_reasons"), list)
                    else []
                ),
                *stale_reasons,
            ]
        initial_status = str(payload.get("read_model_status") or "fresh")
        if not loaded_from_cache and cacheable_query and initial_status == "fresh":
            resolved_cache_key = (
                self._initial_cache_key_from_version(cache_version=payload_version, scope_key=scope_key)
                if payload_version and callable(self._initial_cache_key_from_version)
                else None
            )
            set_cached = getattr(self._redis_helper, "set_json", None)
            if resolved_cache_key and callable(set_cached):
                try:
                    set_cached(
                        resolved_cache_key,
                        {"payload": dict(payload)},
                        ttl_seconds=self._groups_redis_ttl_seconds(),
                    )
                except Exception:
                    pass
        if "oa_status" not in payload and callable(self._oa_status_provider):
            payload["oa_status"] = self._serialize_value(self._oa_status_provider())
        if initial_status != "fresh":
            if initial_status != "refreshing" and refresh_status not in {"refreshing", "stale"}:
                self._enqueue_refresh(scope_key, reason="api_initial_page_stale")
            self._emit_status_metric(
                endpoint="/api/workbench",
                scope_key=scope_key,
                read_model_status=initial_status,
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
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: dict[str, object] | None = None,
        time_filters: dict[str, object] | None = None,
        expected_read_model_version: str | None = None,
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
        expected_version = str(expected_read_model_version or "").strip()
        current_version = (
            str(
                refresh_status_payload.get("read_model_version")
                or refresh_status_payload.get("active_generation_id")
                or ""
            ).strip()
            if isinstance(refresh_status_payload, dict)
            else ""
        )
        if expected_version and current_version and expected_version != current_version:
            return WorkbenchQueryResult(
                HTTPStatus.CONFLICT,
                {
                    "error": "workbench_read_model_version_conflict",
                    "scope_key": scope_key,
                    "zone": zone,
                    "expected_read_model_version": expected_version,
                    "read_model_version": current_version,
                },
            )
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
        repository_kwargs = dict(cache_kwargs)
        if expected_version:
            repository_kwargs["expected_read_model_version"] = expected_version
        try:
            payload = get_groups_page(**repository_kwargs)
        except Exception as error:
            if isinstance(error, WorkbenchReadModelVersionConflictError):
                return WorkbenchQueryResult(
                    HTTPStatus.CONFLICT,
                    {
                        "error": "workbench_read_model_version_conflict",
                        "scope_key": scope_key,
                        "zone": zone,
                        "expected_read_model_version": error.expected,
                        "read_model_version": error.current,
                    },
                )
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
        refresh_status_value = (
            str(refresh_status_payload.get("read_model_status") or "")
            if isinstance(refresh_status_payload, dict)
            else ""
        )
        refresh_status_enqueued = bool(refresh_status_value and refresh_status_value != "fresh")
        if refresh_status_value and refresh_status_value != "fresh":
            payload["read_model_status"] = refresh_status_value
            refresh_stale_reasons = refresh_status_payload.get("read_model_stale_reasons")
            if isinstance(refresh_stale_reasons, list) and refresh_stale_reasons:
                payload["read_model_stale_reasons"] = [
                    *list(payload.get("read_model_stale_reasons") if isinstance(payload.get("read_model_stale_reasons"), list) else []),
                    *refresh_stale_reasons,
                ]
        stale_reasons = self._stale_reasons(payload.get("source_versions"), scope_key=scope_key)
        if stale_reasons:
            payload["read_model_status"] = "stale"
            payload["read_model_stale_reasons"] = [
                *list(payload.get("read_model_stale_reasons") if isinstance(payload.get("read_model_stale_reasons"), list) else []),
                *stale_reasons,
            ]
        groups_status = str(payload.get("read_model_status") or "fresh")
        if groups_status != "fresh":
            if not refresh_status_enqueued:
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

    def group_detail(
        self,
        month: str | None,
        *,
        zone: str,
        group_id: str,
        expected_read_model_version: str | None = None,
    ) -> WorkbenchQueryResult:
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
            group = get_group_detail(
                scope_key=scope_key,
                zone=zone,
                group_id=group_id,
                expected_read_model_version=expected_read_model_version,
            )
        except Exception as error:
            if isinstance(error, WorkbenchReadModelVersionConflictError):
                return WorkbenchQueryResult(
                    HTTPStatus.CONFLICT,
                    {
                        "error": "workbench_read_model_version_conflict",
                        "message": str(error),
                        "scope_key": scope_key,
                        "zone": zone,
                        "group_id": group_id,
                        "expected_read_model_version": error.expected,
                        "read_model_version": error.current,
                    },
                )
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
        group_scope_key = str(group.get("scope_key") or scope_key)
        stale_reasons = self._stale_reasons(group.get("source_versions"), scope_key=group_scope_key)
        group_status = "stale" if stale_reasons else str(group.get("read_model_status") or "fresh")
        if group_status != "fresh":
            reason = "api_group_detail_source_versions_stale" if stale_reasons else "api_group_detail_stale"
            if group_status != "refreshing":
                self._enqueue_refresh(group_scope_key, reason=reason)
            self._emit_status_metric(
                endpoint="/api/workbench/groups/detail",
                scope_key=group_scope_key,
                read_model_status=group_status,
                reason="sql_status",
            )
            payload: dict[str, object] = {
                "error": "workbench_group_not_found",
                "scope_key": scope_key,
                "zone": zone,
                "group_id": group_id,
                "read_model_status": group_status,
            }
            if stale_reasons:
                payload["read_model_stale_reasons"] = [
                    *list(group.get("read_model_stale_reasons") if isinstance(group.get("read_model_stale_reasons"), list) else []),
                    *stale_reasons,
                ]
            return WorkbenchQueryResult(HTTPStatus.NOT_FOUND, payload)
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

    def row_detail(
        self,
        month: str | None,
        *,
        row_id: str,
        expected_read_model_version: str | None = None,
    ) -> WorkbenchQueryResult:
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
        repository_kwargs: dict[str, object] = {
            "scope_key": scope_key,
            "row_id": normalized_row_id,
        }
        expected_version = str(expected_read_model_version or "").strip()
        if expected_version:
            repository_kwargs["expected_read_model_version"] = expected_version
        try:
            payload = get_row_detail(**repository_kwargs)
        except Exception as error:
            if isinstance(error, WorkbenchReadModelVersionConflictError):
                return WorkbenchQueryResult(
                    HTTPStatus.CONFLICT,
                    {
                        "error": "workbench_read_model_version_conflict",
                        "scope_key": scope_key,
                        "row_id": normalized_row_id,
                        "expected_read_model_version": error.expected,
                        "read_model_version": error.current,
                    },
                )
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

    def write_precondition(
        self,
        month: str | None,
        *,
        expected_read_model_version: object,
    ) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        expected_version = str(expected_read_model_version or "").strip()
        if not expected_version:
            return WorkbenchQueryResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "expected_read_model_version_required",
                    "message": "expected_read_model_version is required.",
                    "scope_key": scope_key,
                },
            )
        try:
            status_payload = self._groups_refresh_status_payload(scope_key)
        except Exception as error:
            if self._transient_read_model_error(error):
                return self._read_model_temporarily_unavailable_result(
                    endpoint="/api/workbench/actions",
                    scope_key=scope_key,
                )
            raise
        if not isinstance(status_payload, dict):
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "workbench_read_model_unavailable",
                    "message": "Workbench read model status is unavailable.",
                    "read_model_status": "unavailable",
                    "scope_key": scope_key,
                    "retryable": True,
                },
            )

        read_model_status = str(status_payload.get("read_model_status") or "unavailable").strip()
        read_model_version = str(
            status_payload.get("read_model_version")
            or status_payload.get("active_generation_id")
            or ""
        ).strip()
        response_context = {
            "read_model_status": read_model_status,
            "read_model_version": read_model_version or None,
            "scope_key": scope_key,
        }
        if not read_model_version:
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "workbench_read_model_unavailable",
                    "message": "Workbench active generation version is unavailable.",
                    **response_context,
                    "retryable": True,
                },
            )
        if read_model_version != expected_version:
            return WorkbenchQueryResult(
                HTTPStatus.CONFLICT,
                {
                    "error": "workbench_read_model_version_conflict",
                    "message": "Workbench read model version changed; reload and retry.",
                    **response_context,
                    "retryable": True,
                },
            )
        if read_model_status in {"refreshing", "stale"}:
            return WorkbenchQueryResult(
                HTTPStatus.CONFLICT,
                {
                    "error": "workbench_read_model_not_fresh",
                    "message": "Workbench read model is not fresh; reload after refresh completes.",
                    **response_context,
                    "retryable": True,
                },
            )
        if read_model_status != "fresh":
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "workbench_read_model_unavailable",
                    "message": "Workbench read model is unavailable.",
                    **response_context,
                    "retryable": True,
                },
            )
        return WorkbenchQueryResult(HTTPStatus.OK, response_context)

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
        refresh_status = str(refresh_status_payload.get("read_model_status") or "fresh")
        if refresh_status not in {"fresh", "refreshing"}:
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
            read_model_status="unavailable",
            reason="query_timeout",
        )
        return WorkbenchQueryResult(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "query_timeout",
                "read_model_status": "unavailable",
                "retryable": True,
                "scope_key": scope_key,
                "message": "Workbench SQL query timed out; retry the request later.",
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
