from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable

from fin_ops_platform.services.workbench_relation_preview_policy import (
    WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS,
    WorkbenchRelationPreviewSelectionError,
)


@dataclass(frozen=True)
class WorkbenchQueryResult:
    status_code: HTTPStatus
    payload: dict[str, object]


class WorkbenchQueryFacade:
    """Application service for Workbench page reads from canonical facts."""

    def __init__(
        self,
        *,
        repository: object | None,
        scope_key_for_month: Callable[[str | None], str],
    ) -> None:
        self._repository = repository
        self._scope_key_for_month = scope_key_for_month

    def initial_page(
        self,
        month: str | None,
        *,
        paired_query: dict[str, object] | None = None,
        unpaired_query: dict[str, object] | None = None,
    ) -> WorkbenchQueryResult:
        current_month, scope_key = self._scope(month)
        read = getattr(self._repository, "get_workbench_initial_page", None)
        if not callable(read):
            return self._unavailable(scope_key)
        payload = read(
            scope_key=scope_key,
            paired_query=paired_query,
            unpaired_query=unpaired_query,
        )
        if not isinstance(payload, dict):
            return self._unavailable(scope_key)
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {**payload, "month": current_month, "scope_key": scope_key},
        )

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
    ) -> WorkbenchQueryResult:
        current_month, scope_key = self._scope(month)
        read = getattr(self._repository, "get_workbench_groups_page", None)
        if not callable(read):
            return self._unavailable(scope_key)
        payload = read(
            scope_key=scope_key,
            zone=zone,
            page=page,
            page_size=page_size,
            status=status,
            source_kind=source_kind,
            search=search,
            sort=sort,
            detail_level=detail_level,
            column_filters=column_filters,
            time_filters=time_filters,
        )
        if not isinstance(payload, dict):
            return self._unavailable(scope_key)
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {
                **payload,
                "month": current_month,
                "scope_key": scope_key,
                "zone": zone,
            },
        )

    def group_detail(
        self,
        month: str | None,
        *,
        zone: str,
        group_id: str,
        detail_key: str | None = None,
    ) -> WorkbenchQueryResult:
        _, scope_key = self._scope(month)
        read = getattr(self._repository, "get_workbench_group_detail", None)
        if not callable(read):
            return self._unavailable(scope_key)
        payload = read(
            scope_key=scope_key,
            zone=zone,
            group_id=group_id,
            detail_key=detail_key,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("group"), dict):
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "workbench_group_not_found",
                    "scope_key": scope_key,
                    "zone": zone,
                    "group_id": group_id,
                },
            )
        return WorkbenchQueryResult(HTTPStatus.OK, payload)

    def row_detail(
        self,
        month: str | None,
        *,
        row_id: str,
    ) -> WorkbenchQueryResult:
        _, scope_key = self._scope(month)
        normalized_row_id = str(row_id or "").strip()
        read = getattr(self._repository, "get_workbench_row_detail", None)
        if not callable(read):
            return self._unavailable(scope_key)
        if not normalized_row_id:
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "workbench_row_not_found",
                    "scope_key": scope_key,
                    "row_id": normalized_row_id,
                },
            )
        payload = read(scope_key=scope_key, row_id=normalized_row_id)
        if not isinstance(payload, dict) or not isinstance(payload.get("row"), dict):
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "workbench_row_not_found",
                    "scope_key": scope_key,
                    "row_id": normalized_row_id,
                },
            )
        return WorkbenchQueryResult(HTTPStatus.OK, payload)

    def relation_preview_selection(
        self,
        month: str | None,
        *,
        row_ids: list[str],
    ) -> WorkbenchQueryResult:
        current_month, scope_key = self._scope(month)
        normalized_row_ids = list(
            dict.fromkeys(
                str(row_id).strip()
                for row_id in list(row_ids or [])
                if str(row_id).strip()
            )
        )
        if not normalized_row_ids:
            return WorkbenchQueryResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "relation_preview_selection_required",
                    "message": "请至少选择一条工作台记录。",
                    "scope_key": scope_key,
                },
            )
        if len(normalized_row_ids) > WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS:
            return WorkbenchQueryResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "relation_preview_selection_too_large",
                    "message": (
                        f"单次预览最多选择 "
                        f"{WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS} 条记录。"
                    ),
                    "scope_key": scope_key,
                },
            )
        read = getattr(
            self._repository,
            "get_workbench_relation_preview_selection",
            None,
        )
        if not callable(read):
            return self._unavailable(scope_key)
        try:
            payload = read(scope_key=scope_key, row_ids=normalized_row_ids)
        except WorkbenchRelationPreviewSelectionError as error:
            return WorkbenchQueryResult(
                HTTPStatus.CONFLICT,
                {
                    "error": error.code,
                    "message": str(error),
                    "scope_key": scope_key,
                },
            )
        if not isinstance(payload, dict):
            return self._unavailable(scope_key)
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {
                **payload,
                "month": current_month,
                "scope_key": scope_key,
            },
        )

    def _scope(self, month: str | None) -> tuple[str, str]:
        current_month = str(month or "").strip() or "all"
        return current_month, self._scope_key_for_month(current_month)

    @staticmethod
    def _unavailable(scope_key: str) -> WorkbenchQueryResult:
        return WorkbenchQueryResult(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "workbench_canonical_query_unavailable",
                "message": "关联台 PostgreSQL 查询暂时不可用。",
                "scope_key": scope_key,
            },
        )
