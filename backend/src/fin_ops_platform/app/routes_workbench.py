from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.workbench_action_service import WorkbenchActionService
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
