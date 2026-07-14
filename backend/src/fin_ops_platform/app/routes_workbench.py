from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable, Iterable

from fin_ops_platform.services.workbench_groups_page_cache import (
    normalize_workbench_group_detail_level,
    normalize_workbench_group_search_mode,
    stable_json_value,
)
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


class WorkbenchRowDetailApiRoutes:
    """Read-only owner for Workbench row detail fallback orchestration."""

    def __init__(
        self,
        *,
        etc_summary_row_detail: Callable[[str], dict[str, object] | None],
        live_row_detail: Callable[[str], dict[str, object]],
        row_month_scope_from_row_id: Callable[[str], str | None],
        cached_rows_resolver: Callable[..., dict[str, dict[str, object]]],
        query_facade_provider: Callable[[], Any | None],
        looks_like_oa_row_id: Callable[[str], bool],
        legacy_row_detail: Callable[[str], dict[str, object]],
        requires_sql_read_model_runtime: Callable[[], bool],
        apply_row_override: Callable[[dict[str, object]], dict[str, object]],
    ) -> None:
        self._etc_summary_row_detail = etc_summary_row_detail
        self._live_row_detail = live_row_detail
        self._row_month_scope_from_row_id = row_month_scope_from_row_id
        self._cached_rows_resolver = cached_rows_resolver
        self._query_facade_provider = query_facade_provider
        self._looks_like_oa_row_id = looks_like_oa_row_id
        self._legacy_row_detail = legacy_row_detail
        self._requires_sql_read_model_runtime = requires_sql_read_model_runtime
        self._apply_row_override = apply_row_override

    def get_payload(self, row_id: str, *, month: str | None = None) -> dict[str, object]:
        etc_summary_row = self._etc_summary_row_detail(row_id)
        if etc_summary_row is not None:
            return {"row": self._apply_row_override(etc_summary_row)}

        month_hint = str(month).strip() if month not in (None, "") else self._row_month_scope_from_row_id(row_id)
        fallback_allowed = self._legacy_route_fallback_allowed(row_id)
        live_checked = False
        if month_hint is None and fallback_allowed:
            live_checked = True
            try:
                return {"row": self._apply_row_override(self._live_row_detail(row_id))}
            except KeyError:
                pass

        cached_rows = self._cached_rows_resolver([row_id], month_hint=month_hint)
        if row_id in cached_rows:
            payload = {"row": cached_rows[row_id]}
        elif query_facade_row := self._row_detail_from_query_facade(row_id, month_hint=month_hint):
            payload = {"row": query_facade_row}
        elif month_hint is None and self._looks_like_oa_row_id(row_id):
            raise KeyError(row_id)
        elif fallback_allowed:
            if live_checked:
                payload = self._legacy_row_detail(row_id)
            else:
                try:
                    payload = {"row": self._live_row_detail(row_id)}
                except KeyError:
                    payload = self._legacy_row_detail(row_id)
        else:
            raise KeyError(row_id)
        row = payload.get("row")
        if not isinstance(row, dict):
            raise KeyError(row_id)
        payload["row"] = self._apply_row_override(row)
        return payload

    def _row_detail_from_query_facade(
        self,
        row_id: str,
        *,
        month_hint: str | None,
    ) -> dict[str, object] | None:
        facade = self._query_facade_provider()
        if facade is None:
            return None
        try:
            result = facade.row_detail(month_hint, row_id=row_id)
        except AttributeError:
            return None
        if result.status_code != HTTPStatus.OK:
            return None
        payload = result.payload if isinstance(result.payload, dict) else {}
        row = payload.get("row")
        return row if isinstance(row, dict) else None

    def _legacy_route_fallback_allowed(self, row_id: str) -> bool:
        return not self._requires_sql_read_model_runtime()


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
    """Read-only owner for Workbench summary and grouped list request mapping."""

    def __init__(self, *, query_facade_provider: Callable[[], Any]) -> None:
        self._query_facade_provider = query_facade_provider

    def summary(self, month: str | None) -> tuple[HTTPStatus, dict[str, object]]:
        result = self._query_facade_provider().summary(month)
        return result.status_code, result.payload

    def refresh_status(self, month: str | None) -> tuple[HTTPStatus, dict[str, object]]:
        result = self._query_facade_provider().refresh_status(month)
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
        result = self._query_facade_provider().groups(
            current_month,
            zone=normalized_zone,
            page=page,
            page_size=page_size,
            status=status,
            source_kind=source_kind,
            search=search,
            search_mode=normalize_workbench_group_search_mode(search_mode),
            search_by_pane=normalized_search_by_pane,
            sort=sort,
            detail_level=normalize_workbench_group_detail_level(detail_level),
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
        )
        return result.status_code, result.payload

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


class WorkbenchApiRoutes:
    def __init__(self, query_service: WorkbenchQueryService) -> None:
        self._query_service = query_service

    def get_workbench(self, month: str) -> dict[str, object]:
        return self._query_service.get_workbench(month)

    def get_row_detail(self, row_id: str) -> dict[str, object]:
        return {"row": self._query_service.get_row_detail(row_id)}
