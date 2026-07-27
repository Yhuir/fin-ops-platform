from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from time import monotonic
from typing import Any, Callable

from fin_ops_platform.app.auth import OARequestSession, actor_id_for_session
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.cost_statistics_query_service import (
    CostStatisticsExportLimitError,
)

ReadSessionResolver = Callable[[dict[str, str] | None], tuple[OARequestSession | None, Any | None]]
WriteSessionResolver = Callable[[dict[str, str] | None], tuple[OARequestSession | None, Any | None]]
JsonBodyLoader = Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]]


class CostStatisticsApiRoutes:
    def __init__(
        self,
        *,
        query_service: Any,
        json_response: Callable[..., Any],
        file_response: Callable[[str, bytes], Any],
        metric_emitter: Callable[..., None] | None = None,
        entry_count: Callable[[dict[str, Any]], int] | None = None,
        duration_ms: Callable[[float], float] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        optional_bool_parser: Callable[[str | None], bool] | None = None,
        app_settings_service: Any | None = None,
        resolve_read_session: ReadSessionResolver | None = None,
        resolve_write_session: WriteSessionResolver | None = None,
        load_json_body: JsonBodyLoader | None = None,
    ) -> None:
        self._query_service = query_service
        self._json_response = json_response
        self._file_response = file_response
        self._metric_emitter = metric_emitter
        self._entry_count = entry_count or _explorer_entry_count
        self._duration_ms = duration_ms or (lambda started_at: (monotonic() - started_at) * 1000)
        self._now_provider = now_provider or datetime.now
        self._optional_bool_parser = optional_bool_parser or _parse_optional_bool_default_true
        self._app_settings_service = app_settings_service
        self._resolve_read_session = resolve_read_session
        self._resolve_write_session = resolve_write_session
        self._load_json_body = load_json_body

    def route(
        self,
        method: str,
        route_path: str,
        query: dict[str, list[str]],
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any | None:
        if method == "GET" and route_path == "/api/cost-statistics/tag-rules":
            return self.handle_tag_rules(headers)
        if method == "PUT" and route_path == "/api/cost-statistics/tag-rules":
            return self.handle_update_tag_rules(body, headers)
        if method == "GET" and route_path == "/api/cost-statistics/explorer":
            return self.handle_explorer(
                scope=query.get("scope", [None])[0],
                view=query.get("view", [None])[0],
                project_scope=query.get("project_scope", [None])[0],
                project_name=query.get("project_name", [None])[0],
                expense_type=query.get("expense_type", [None])[0],
                payment_account_label=query.get("payment_account_label", [None])[0],
                bank_tag_primary_label=query.get("bank_tag_primary_label", [None])[0],
                bank_tag_sub_label=query.get("bank_tag_sub_label", [None])[0],
                cursor=query.get("cursor", [None])[0],
                page_size=query.get("page_size", [None])[0],
                include_statistics=query.get("include_statistics", [None])[0],
                if_none_match=_header(headers, "if-none-match"),
            )
        if method == "GET" and route_path == "/api/cost-statistics/export-preview":
            return self.handle_export_preview(
                month=query.get("month", [None])[0],
                view=query.get("view", [None])[0],
                project_names=query.get("project_name", []),
                expense_types=query.get("expense_type", []),
                start_month=query.get("start_month", [None])[0],
                end_month=query.get("end_month", [None])[0],
                start_date=query.get("start_date", [None])[0],
                end_date=query.get("end_date", [None])[0],
                aggregate_by=query.get("aggregate_by", [None])[0],
                project_scope=query.get("project_scope", [None])[0],
            )
        if method == "GET" and route_path == "/api/cost-statistics/export":
            return self.handle_export(
                month=query.get("month", [None])[0],
                view=query.get("view", [None])[0],
                project_names=query.get("project_name", []),
                expense_types=query.get("expense_type", []),
                transaction_id=query.get("transaction_id", [None])[0],
                start_month=query.get("start_month", [None])[0],
                end_month=query.get("end_month", [None])[0],
                start_date=query.get("start_date", [None])[0],
                end_date=query.get("end_date", [None])[0],
                aggregate_by=query.get("aggregate_by", [None])[0],
                include_oa_details=self._optional_bool_parser(query.get("include_oa_details", [None])[0]),
                include_invoice_details=self._optional_bool_parser(query.get("include_invoice_details", [None])[0]),
                include_exception_rows=self._optional_bool_parser(query.get("include_exception_rows", [None])[0]),
                include_ignored_rows=self._optional_bool_parser(query.get("include_ignored_rows", [None])[0]),
                include_expense_content_summary=self._optional_bool_parser(
                    query.get("include_expense_content_summary", [None])[0]
                ),
                sort_by=query.get("sort_by", [None])[0],
                project_scope=query.get("project_scope", [None])[0],
            )
        if method == "GET" and route_path.startswith("/api/cost-statistics/transactions/"):
            transaction_id = route_path.rsplit("/", 1)[-1]
            return self.handle_transaction(
                transaction_id,
                query.get("project_scope", [None])[0],
                query.get("view", [None])[0],
                query.get("scope", [None])[0],
            )
        return None

    def handle_tag_rules(self, headers: dict[str, str] | None) -> Any:
        session, error = self._read_session(headers)
        if error is not None:
            return error
        service = self._settings_service()
        return self._json_response(
            HTTPStatus.OK,
            service.get_cost_statistics_tag_selection_payload(
                can_save=bool(session is None or session.can_mutate_data),
            ),
        )

    def handle_update_tag_rules(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        session, error = self._write_session(headers)
        if error is not None:
            return error
        payload, body_error = self._load_body(body)
        if body_error is not None:
            return body_error
        service = self._settings_service()
        try:
            result = service.update_cost_statistics_tag_selection(
                payload,
                actor_id=actor_id_for_session(session) if session is not None else str(payload.get("actor_id") or "cost_statistics"),
            )
        except AppSettingsValidationError as exc:
            status = (
                HTTPStatus.CONFLICT
                if exc.error_code == "cost_statistics_tag_selection_version_conflict"
                else HTTPStatus.BAD_REQUEST
            )
            return self._json_response(status, {"error": exc.error_code, "message": str(exc)})
        return self._json_response(HTTPStatus.OK, result)

    def handle_explorer(
        self,
        *,
        scope: str | None,
        view: str | None,
        project_scope: str | None,
        project_name: str | None,
        expense_type: str | None,
        payment_account_label: str | None,
        bank_tag_primary_label: str | None,
        bank_tag_sub_label: str | None,
        cursor: str | None,
        page_size: str | None,
        include_statistics: str | None,
        if_none_match: str | None,
    ) -> Any:
        current_scope = scope or self._now_provider().strftime("%Y-%m")
        started_at = monotonic()
        cache_hit = False
        try:
            normalized_project_scope = self._normalize_project_scope(project_scope)
            if (
                include_statistics is not None
                and str(include_statistics).strip().lower()
                not in {"0", "false", "no", "off", "1", "true", "yes", "on"}
            ):
                raise ValueError("include_statistics must be true or false")
            payload, cache_hit, etag, not_modified = self._query_service.get_explorer_page(
                scope=current_scope,
                view=str(view or ""),
                project_scope=normalized_project_scope,
                filters={
                    "project_name": project_name,
                    "expense_type": expense_type,
                    "payment_account_label": payment_account_label,
                    "bank_tag_primary_label": bank_tag_primary_label,
                    "bank_tag_sub_label": bank_tag_sub_label,
                },
                cursor=cursor,
                page_size=int(page_size or 50),
                include_statistics=self._optional_bool_parser(include_statistics),
                if_none_match=if_none_match,
            )
        except ValueError as error:
            return self._page_query_error_response(error)
        if self._metric_emitter is not None:
            self._metric_emitter(
                month=current_scope,
                project_scope=normalized_project_scope,
                cache_hit=cache_hit,
                duration_ms=self._duration_ms(started_at),
                entry_count=self._entry_count(payload),
            )
        response_headers = {
            "Cache-Control": "private, no-cache",
            "Vary": "Authorization, Cookie",
        }
        if etag:
            response_headers["ETag"] = etag
        if not_modified:
            return self._json_response(HTTPStatus.NOT_MODIFIED, {}, response_headers)
        return self._json_response(HTTPStatus.OK, payload, response_headers)

    def handle_export(
        self,
        *,
        month: str | None,
        view: str | None,
        project_names: list[str] | None,
        expense_types: list[str] | None,
        transaction_id: str | None,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        aggregate_by: str | None = None,
        include_oa_details: bool = True,
        include_invoice_details: bool = True,
        include_exception_rows: bool = True,
        include_ignored_rows: bool = True,
        include_expense_content_summary: bool = True,
        sort_by: str | None = None,
        project_scope: str | None = None,
    ) -> Any:
        current_month = month or self._now_provider().strftime("%Y-%m")
        if view not in {"month", "time", "bank_tag", "project", "expense_type", "transaction"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_cost_statistics_export_request",
                    "message": "view must be month, time, bank_tag, project, expense_type, or transaction.",
                },
            )
        try:
            normalized_project_scope = self._normalize_project_scope(project_scope)
            filename, content = self._query_service.export_view(
                month=current_month,
                view=view,
                project_names=project_names,
                expense_types=expense_types,
                transaction_id=transaction_id,
                start_month=start_month,
                end_month=end_month,
                start_date=start_date,
                end_date=end_date,
                aggregate_by=aggregate_by,
                include_oa_details=include_oa_details,
                include_invoice_details=include_invoice_details,
                include_exception_rows=include_exception_rows,
                include_ignored_rows=include_ignored_rows,
                include_expense_content_summary=include_expense_content_summary,
                sort_by=sort_by or "time",
                project_scope=normalized_project_scope,
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "cost_statistics_transaction_not_found", "transaction_id": transaction_id},
            )
        except CostStatisticsExportLimitError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": error.error_code, "message": str(error), "details": dict(error.details)},
            )
        except ValueError as error:
            if str(error) == "project_scope must be active or all":
                return self._project_scope_error_response(error)
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cost_statistics_export_request", "message": str(error)},
            )
        return self._file_response(filename, content)

    def handle_export_preview(
        self,
        *,
        month: str | None,
        view: str | None,
        project_names: list[str] | None,
        expense_types: list[str] | None,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        aggregate_by: str | None = None,
        project_scope: str | None = None,
    ) -> Any:
        current_month = month or self._now_provider().strftime("%Y-%m")
        if view not in {"time", "bank_tag", "project", "expense_type"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_cost_statistics_export_preview_request",
                    "message": "view must be time, bank_tag, project, or expense_type.",
                },
            )
        try:
            normalized_project_scope = self._normalize_project_scope(project_scope)
            payload = self._query_service.get_export_preview(
                month=current_month,
                view=view,
                project_names=project_names,
                expense_types=expense_types,
                start_month=start_month,
                end_month=end_month,
                start_date=start_date,
                end_date=end_date,
                aggregate_by=aggregate_by,
                project_scope=normalized_project_scope,
            )
        except CostStatisticsExportLimitError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": error.error_code, "message": str(error), "details": dict(error.details)},
            )
        except ValueError as error:
            if str(error) == "project_scope must be active or all":
                return self._project_scope_error_response(error)
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cost_statistics_export_preview_request", "message": str(error)},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def handle_transaction(
        self,
        transaction_id: str,
        project_scope: str | None,
        view: str | None,
        scope: str | None,
    ) -> Any:
        normalized_view = str(view or "").strip().lower()
        if normalized_view not in {"time", "project", "bank", "expense_type", "bank_tag"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_cost_statistics_transaction_request",
                    "message": "view must be time, project, bank, expense_type, or bank_tag.",
                },
            )
        try:
            normalized_project_scope = self._normalize_project_scope(project_scope)
            payload = self._query_service.get_transaction_detail(
                transaction_id,
                project_scope=normalized_project_scope,
                view=normalized_view,
                scope=str(scope or ""),
            )
        except ValueError as error:
            if str(error) == "project_scope must be active or all":
                return self._project_scope_error_response(error)
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_cost_statistics_transaction_request",
                    "message": str(error),
                },
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "cost_statistics_transaction_not_found", "transaction_id": transaction_id},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _settings_service(self) -> Any:
        if self._app_settings_service is None:
            raise RuntimeError("Cost statistics app settings service is not configured.")
        return self._app_settings_service

    def _read_session(self, headers: dict[str, str] | None) -> tuple[OARequestSession | None, Any | None]:
        if self._resolve_read_session is None:
            return None, None
        return self._resolve_read_session(headers)

    def _write_session(self, headers: dict[str, str] | None) -> tuple[OARequestSession | None, Any | None]:
        if self._resolve_write_session is None:
            return None, None
        return self._resolve_write_session(headers)

    def _load_body(self, body: str | bytes | None) -> tuple[dict[str, Any], Any | None]:
        if self._load_json_body is None:
            raise RuntimeError("Cost statistics JSON body loader is not configured.")
        return self._load_json_body(body)

    @staticmethod
    def _normalize_project_scope(project_scope: str | None) -> str:
        normalized_project_scope = str(project_scope or "active").strip().lower()
        if normalized_project_scope not in {"active", "all"}:
            raise ValueError("project_scope must be active or all")
        return normalized_project_scope

    def _project_scope_error_response(self, error: ValueError) -> Any:
        return self._json_response(
            HTTPStatus.BAD_REQUEST,
            {
                "error": "invalid_cost_statistics_project_scope",
                "message": str(error),
            },
        )

    def _page_query_error_response(self, error: ValueError) -> Any:
        message = str(error)
        if "project_scope" in message:
            return self._project_scope_error_response(error)
        error_code = "invalid_cost_statistics_cursor" if "cursor" in message else "invalid_cost_statistics_query"
        return self._json_response(HTTPStatus.BAD_REQUEST, {"error": error_code, "message": message})


def _explorer_entry_count(payload: dict[str, Any]) -> int:
    rows = payload.get("rows")
    if isinstance(rows, list):
        return len(rows)
    time_rows = payload.get("time_rows")
    if isinstance(time_rows, list):
        return len(time_rows)
    summary = payload.get("summary")
    if isinstance(summary, dict):
        raw_count = summary.get("transaction_count", summary.get("row_count", 0))
        try:
            return int(raw_count)
        except (TypeError, ValueError):
            return 0
    return 0


def _parse_optional_bool_default_true(value: str | None) -> bool:
    if value is None:
        return True
    normalized = str(value).strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    return True


def _header(headers: dict[str, str] | None, name: str) -> str | None:
    normalized_name = name.strip().lower()
    for key, value in (headers or {}).items():
        if str(key).strip().lower() == normalized_name:
            return str(value)
    return None
