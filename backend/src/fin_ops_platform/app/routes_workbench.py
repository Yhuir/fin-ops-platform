from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable, Iterable

from fin_ops_platform.services.workbench_groups_page_cache import (
    normalize_workbench_group_detail_level,
    normalize_workbench_group_search_mode,
    stable_json_value,
)


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
        search_mode: str | None = None,
        search_by_pane: str | None = None,
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: str | None = None,
        time_filters: str | None = None,
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
            normalized_search_by_pane = self._normalize_json_query_param(search_by_pane, "search_by_pane")
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
            "search": search,
            "search_mode": normalize_workbench_group_search_mode(search_mode),
            "search_by_pane": normalized_search_by_pane,
            "sort": sort,
            "detail_level": normalize_workbench_group_detail_level(detail_level),
            "column_filters": normalized_column_filters,
            "time_filters": normalized_time_filters,
        }
        expected_version = str(expected_read_model_version or "").strip()
        if expected_version:
            kwargs["expected_read_model_version"] = expected_version
        result = self._query_facade_provider().groups(current_month, **kwargs)
        return result.status_code, result.payload

    @staticmethod
    def _normalize_initial_query_param(value: str | None, name: str) -> dict[str, object]:
        normalized = WorkbenchReadApiRoutes._normalize_json_query_param(value, name)
        allowed_string_fields = {"status", "source_kind", "search", "search_mode", "sort"}
        allowed_object_fields = {"search_by_pane", "column_filters", "time_filters"}
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
        search_mode = str(normalized.get("search_mode") or "").strip().lower()
        if search_mode and search_mode not in {"pane", "linked_context"}:
            raise ValueError(f"{name}.search_mode must be pane or linked_context.")
        if search_mode:
            normalized["search_mode"] = search_mode
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


class WorkbenchEventsApiRoutes:
    """Read-only owner for Workbench refresh status SSE stream construction."""

    def __init__(
        self,
        *,
        scope_key_for_month: Callable[[str], str],
        status_payload_for_scope: Callable[[str], dict[str, object]],
        event_name_for_payload: Callable[[dict[str, object]], str],
        serialize_sse_event: Callable[[str, dict[str, object]], str],
        mark_stream_started: Callable[[str], None],
        mark_stream_closed: Callable[[str], None],
        sleep_seconds: Callable[[float], None],
    ) -> None:
        self._scope_key_for_month = scope_key_for_month
        self._status_payload_for_scope = status_payload_for_scope
        self._event_name_for_payload = event_name_for_payload
        self._serialize_sse_event = serialize_sse_event
        self._mark_stream_started = mark_stream_started
        self._mark_stream_closed = mark_stream_closed
        self._sleep_seconds = sleep_seconds

    def events(self, month: str | None) -> tuple[HTTPStatus, Iterable[str], dict[str, str]]:
        current_month = month or "all"
        scope_key = self._scope_key_for_month(current_month)

        def event_stream() -> Iterable[str]:
            self._mark_stream_started(scope_key)
            try:
                while True:
                    status_payload = self._status_payload_for_scope(scope_key)
                    event_name = self._event_name_for_payload(status_payload)
                    yield self._serialize_sse_event(event_name, status_payload)
                    yield self._serialize_sse_event(
                        "heartbeat",
                        {
                            "scope_key": scope_key,
                            "generated_at": status_payload.get("generated_at"),
                            "read_model_status": status_payload.get("read_model_status"),
                        },
                    )
                    self._sleep_seconds(5)
            finally:
                self._mark_stream_closed(scope_key)

        return (
            HTTPStatus.OK,
            event_stream(),
            {
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            },
        )
