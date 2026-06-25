from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from fin_ops_platform.services.workbench_action_service import WorkbenchActionService
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
        route_query_service_provider: Callable[[], Any | None],
        query_service_provider: Callable[[], Any | None],
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
        self._route_query_service_provider = route_query_service_provider
        self._query_service_provider = query_service_provider
        self._apply_row_override = apply_row_override

    def get_payload(self, row_id: str, *, month: str | None = None) -> dict[str, object]:
        etc_summary_row = self._etc_summary_row_detail(row_id)
        if etc_summary_row is not None:
            return {"row": self._apply_row_override(etc_summary_row)}

        try:
            payload = {"row": self._live_row_detail(row_id)}
        except KeyError:
            month_hint = str(month).strip() if month not in (None, "") else self._row_month_scope_from_row_id(row_id)
            cached_rows = self._cached_rows_resolver([row_id], month_hint=month_hint)
            if row_id in cached_rows:
                payload = {"row": cached_rows[row_id]}
            elif query_facade_row := self._row_detail_from_query_facade(row_id, month_hint=month_hint):
                payload = {"row": query_facade_row}
            elif month_hint is None and self._looks_like_oa_row_id(row_id):
                raise KeyError(row_id)
            elif self._legacy_route_fallback_allowed(row_id):
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
        if not self._requires_sql_read_model_runtime():
            return True
        route_query_service = self._route_query_service_provider()
        query_service = route_query_service or self._query_service_provider()
        records_by_id = getattr(query_service, "_records_by_id", None)
        return isinstance(records_by_id, dict) and row_id in records_by_id


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
    ) -> tuple[HTTPStatus, dict[str, object]]:
        current_month = month or "all"
        normalized_zone = str(zone or "").strip()
        normalized_group_id = str(group_id or "").strip()
        if normalized_zone not in {"open", "paired"}:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_zone", "message": "zone must be open or paired."},
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
        if normalized_zone not in {"open", "paired"}:
            return (
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_zone", "message": "zone must be open or paired."},
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


class WorkbenchApiRoutes:
    def __init__(self, query_service: WorkbenchQueryService, action_service: WorkbenchActionService) -> None:
        self._query_service = query_service
        self._action_service = action_service

    def get_workbench(self, month: str) -> dict[str, object]:
        return self._query_service.get_workbench(month)

    def get_row_detail(self, row_id: str) -> dict[str, object]:
        return {"row": self._query_service.get_row_detail(row_id)}

    def confirm_link(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.confirm_link(
            month=str(payload["month"]),
            row_ids=list(payload["row_ids"]),
            case_id=str(payload["case_id"]) if payload.get("case_id") is not None else None,
        )

    def mark_exception(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.mark_exception(
            month=str(payload["month"]),
            row_id=str(payload["row_id"]),
            exception_code=str(payload["exception_code"]),
            comment=str(payload.get("comment")) if payload.get("comment") is not None else None,
        )

    def cancel_link(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.cancel_link(
            month=str(payload["month"]),
            row_id=str(payload["row_id"]),
            comment=str(payload.get("comment")) if payload.get("comment") is not None else None,
        )

    def update_bank_exception(self, payload: dict[str, object]) -> dict[str, object]:
        return self._action_service.update_bank_exception(
            month=str(payload["month"]),
            row_id=str(payload["row_id"]),
            relation_code=str(payload["relation_code"]),
            relation_label=str(payload["relation_label"]),
            comment=str(payload.get("comment")) if payload.get("comment") is not None else None,
        )
