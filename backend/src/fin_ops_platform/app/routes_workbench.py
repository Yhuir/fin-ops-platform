from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.search_query import canonicalize_money_search_query
from fin_ops_platform.services.workbench_groups_page_cache import (
    normalize_workbench_group_detail_level,
    stable_json_value,
)
from fin_ops_platform.services.workbench_filter_options import (
    normalize_workbench_filter_option_target,
)

WORKBENCH_SEARCH_QUERY_MAX_LENGTH = 200


class WorkbenchRowDetailApiRoutes:
    """Read-only owner for Workbench row detail request mapping."""

    def __init__(self, *, query_facade_provider: Callable[[], Any]) -> None:
        self._query_facade_provider = query_facade_provider

    def get_payload(self, row_id: str, *, month: str | None = None) -> dict[str, object]:
        status_code, payload = self.get_result(row_id, month=month)
        if status_code != HTTPStatus.OK:
            raise KeyError(row_id)
        return payload

    def get_result(
        self,
        row_id: str,
        *,
        month: str | None = None,
        expected_read_model_version: str | None = None,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        kwargs: dict[str, object] = {"row_id": row_id}
        expected_version = str(expected_read_model_version or "").strip()
        if expected_version:
            kwargs["expected_read_model_version"] = expected_version
        result = self._query_facade_provider().row_detail(month or "all", **kwargs)
        return result.status_code, result.payload


class WorkbenchGroupDetailApiRoutes:
    """Read-only owner for Workbench group detail HTTP validation and mapping."""

    def __init__(self, *, query_facade_provider: Callable[[], Any]) -> None:
        self._query_facade_provider = query_facade_provider

    def get_detail(
        self,
        month: str | None,
        *,
        zone: str | None,
        group_id: str | None,
        expected_read_model_version: str | None = None,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        current_month = month or "all"
        normalized_zone = str(zone or "").strip()
        normalized_group_id = str(group_id or "").strip()
        if normalized_zone not in {"unpaired", "paired"}:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_zone", "message": "zone must be unpaired or paired."},
            )
        if not normalized_group_id:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_group_detail_request", "message": "group_id is required."},
            )
        result = self._query_facade_provider().group_detail(
            current_month,
            zone=normalized_zone,
            group_id=normalized_group_id,
            expected_read_model_version=str(expected_read_model_version or "").strip() or None,
        )
        return result.status_code, result.payload


class WorkbenchReadApiRoutes:
    """Read-only owner for Workbench initial page and grouped list request mapping."""

    def __init__(self, *, query_facade_provider: Callable[[], Any]) -> None:
        self._query_facade_provider = query_facade_provider

    def refresh_status(self, month: str | None) -> tuple[HTTPStatus, dict[str, object]]:
        result = self._query_facade_provider().refresh_status(month)
        return result.status_code, result.payload

    def initial(
        self,
        month: str | None,
        *,
        paired_query: str | None = None,
        unpaired_query: str | None = None,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        try:
            normalized_paired_query = self._normalize_initial_query_param(paired_query, "paired_query")
            normalized_unpaired_query = self._normalize_initial_query_param(unpaired_query, "unpaired_query")
        except ValueError as error:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_initial_query", "message": str(error)},
            )
        result = self._query_facade_provider().initial_page(
            month,
            paired_query=normalized_paired_query,
            unpaired_query=normalized_unpaired_query,
        )
        return result.status_code, result.payload

    def groups(
        self,
        month: str | None,
        *,
        zone: str | None,
        page: str | None = None,
        page_size: str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: str | None = None,
        time_filters: str | None = None,
        exception_bucket: str | None = None,
        expected_read_model_version: str | None = None,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        current_month = month or "all"
        normalized_zone = str(zone or "").strip()
        if normalized_zone not in {"unpaired", "paired"}:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_zone", "message": "zone must be unpaired or paired."},
            )
        try:
            normalized_column_filters = self._normalize_json_query_param(column_filters, "column_filters")
            normalized_time_filters = self._normalize_json_query_param(time_filters, "time_filters")
            normalized_search = self._normalize_search_query(search, "search")
            normalized_exception_bucket = str(exception_bucket or "").strip() or None
            if normalized_exception_bucket not in {None, "active", "processed"}:
                raise ValueError("exception_bucket must be active or processed.")
        except ValueError as error:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_groups_query", "message": str(error)},
            )
        kwargs: dict[str, object] = {
            "zone": normalized_zone,
            "page": page,
            "page_size": page_size,
            "status": status,
            "source_kind": source_kind,
            "search": normalized_search,
            "sort": sort,
            "detail_level": normalize_workbench_group_detail_level(detail_level),
            "column_filters": normalized_column_filters,
            "time_filters": normalized_time_filters,
            "exception_bucket": normalized_exception_bucket,
        }
        expected_version = str(expected_read_model_version or "").strip()
        if expected_version:
            kwargs["expected_read_model_version"] = expected_version
        result = self._query_facade_provider().groups(current_month, **kwargs)
        return result.status_code, result.payload

    def filter_options(
        self,
        month: str | None,
        *,
        zone: str | None,
        pane: str | None,
        facet: str | None = None,
        column: str | None = None,
        option_search: str | None = None,
        page: str | None = None,
        page_size: str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        column_filters: str | None = None,
        time_filters: str | None = None,
        exception_bucket: str | None = None,
        expected_read_model_version: str | None = None,
    ) -> tuple[HTTPStatus, dict[str, object]]:
        current_month = month or "all"
        normalized_zone = str(zone or "").strip()
        if normalized_zone not in {"unpaired", "paired"}:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_zone", "message": "zone must be unpaired or paired."},
            )
        try:
            normalized_pane, normalized_facet, normalized_column = normalize_workbench_filter_option_target(
                pane=pane,
                facet=facet,
                column=column,
            )
            normalized_column_filters = self._normalize_json_query_param(column_filters, "column_filters")
            normalized_time_filters = self._normalize_json_query_param(time_filters, "time_filters")
            normalized_search = self._normalize_search_query(search, "search")
            normalized_option_search = str(option_search or "").strip()
            if len(normalized_option_search) > 100:
                raise ValueError("option_search must not exceed 100 characters.")
            normalized_page = self._normalize_positive_int(page, "page", default=1)
            normalized_page_size = self._normalize_positive_int(page_size, "page_size", default=100, maximum=200)
            normalized_exception_bucket = str(exception_bucket or "").strip() or None
            if normalized_exception_bucket not in {None, "active", "processed"}:
                raise ValueError("exception_bucket must be active or processed.")
        except ValueError as error:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_filter_options_query", "message": str(error)},
            )
        result = self._query_facade_provider().filter_options(
            current_month,
            zone=normalized_zone,
            pane=normalized_pane,
            facet=normalized_facet,
            column=normalized_column,
            option_search=normalized_option_search,
            page=normalized_page,
            page_size=normalized_page_size,
            status=status,
            source_kind=source_kind,
            search=normalized_search,
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
            exception_bucket=normalized_exception_bucket,
            expected_read_model_version=str(expected_read_model_version or "").strip() or None,
        )
        return result.status_code, result.payload

    @staticmethod
    def _normalize_initial_query_param(value: str | None, name: str) -> dict[str, object]:
        normalized = WorkbenchReadApiRoutes._normalize_json_query_param(value, name)
        allowed_string_fields = {"status", "source_kind", "search", "sort"}
        allowed_object_fields = {"column_filters", "time_filters"}
        unknown_fields = sorted(set(normalized) - allowed_string_fields - allowed_object_fields)
        if unknown_fields:
            raise ValueError(f"{name} contains unsupported fields: {', '.join(unknown_fields)}.")
        for field_name in allowed_string_fields:
            field_value = normalized.get(field_name)
            if field_value is not None and not isinstance(field_value, str):
                raise ValueError(f"{name}.{field_name} must be a string.")
        for field_name in allowed_object_fields:
            field_value = normalized.get(field_name)
            if field_value is not None and not isinstance(field_value, dict):
                raise ValueError(f"{name}.{field_name} must be a JSON object.")
        search = WorkbenchReadApiRoutes._normalize_search_query(normalized.get("search"), f"{name}.search")
        if search:
            normalized["search"] = search
        else:
            normalized.pop("search", None)
        return normalized

    @staticmethod
    def _normalize_search_query(value: object, name: str) -> str:
        normalized = canonicalize_money_search_query(value)
        if len(normalized) > WORKBENCH_SEARCH_QUERY_MAX_LENGTH:
            raise ValueError(f"{name} must be at most {WORKBENCH_SEARCH_QUERY_MAX_LENGTH} characters.")
        return normalized

    @staticmethod
    def _normalize_positive_int(
        value: object,
        name: str,
        *,
        default: int,
        maximum: int | None = None,
    ) -> int:
        if value is None or str(value).strip() == "":
            return default
        try:
            normalized = int(str(value).strip())
        except ValueError as error:
            raise ValueError(f"{name} must be an integer.") from error
        if normalized < 1:
            raise ValueError(f"{name} must be at least 1.")
        if maximum is not None and normalized > maximum:
            raise ValueError(f"{name} must not exceed {maximum}.")
        return normalized

    @staticmethod
    def _normalize_json_query_param(value: str | None, name: str) -> dict[str, object]:
        raw_value = str(value or "").strip()
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{name} must be valid JSON object.") from error
        if not isinstance(parsed, dict):
            raise ValueError(f"{name} must be a JSON object.")
        normalized = stable_json_value(parsed)
        return normalized if isinstance(normalized, dict) else {}
