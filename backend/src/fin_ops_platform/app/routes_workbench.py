from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable


WORKBENCH_SEARCH_QUERY_MAX_LENGTH = 200


def normalize_workbench_group_detail_level(value: str | None) -> str:
    return "summary" if str(value or "").strip().lower() == "summary" else "full"


def stable_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): stable_json_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
            if value[key] is not None
        }
    if isinstance(value, list):
        normalized_items = [stable_json_value(item) for item in value]
        if all(not isinstance(item, (dict, list)) for item in normalized_items):
            return sorted(
                normalized_items,
                key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
            )
        return normalized_items
    return value


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
    ) -> tuple[HTTPStatus, dict[str, object]]:
        result = self._query_facade_provider().row_detail(
            month or "all",
            row_id=row_id,
        )
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
        detail_key: str | None = None,
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
            detail_key=str(detail_key or "").strip() or None,
        )
        return result.status_code, result.payload


class WorkbenchReadApiRoutes:
    """Read-only owner for Workbench initial page and grouped list request mapping."""

    def __init__(self, *, query_facade_provider: Callable[[], Any]) -> None:
        self._query_facade_provider = query_facade_provider

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
        }
        result = self._query_facade_provider().groups(current_month, **kwargs)
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
        normalized = str(value or "").strip()
        if len(normalized) > WORKBENCH_SEARCH_QUERY_MAX_LENGTH:
            raise ValueError(f"{name} must be at most {WORKBENCH_SEARCH_QUERY_MAX_LENGTH} characters.")
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
