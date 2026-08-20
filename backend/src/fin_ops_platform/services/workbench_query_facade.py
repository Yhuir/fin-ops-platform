from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable

from fin_ops_platform.services.workbench_direct_query_errors import (
    WorkbenchDirectQueryUnavailable,
    WorkbenchRelationPreviewSelectionError,
)
from fin_ops_platform.services.workbench_filter_options import (
    normalize_workbench_scope_key,
)
from fin_ops_platform.services.workbench_page_cursor import WorkbenchPageCursorError


@dataclass(frozen=True)
class WorkbenchQueryResult:
    status_code: HTTPStatus
    payload: dict[str, object]


class WorkbenchQueryFacade:
    """Direct-only Workbench page query boundary.

    The facade owns request-independent result mapping only.  It has no Redis,
    freshness, generation, refresh enqueue, HTTP, or Application dependency.
    """

    def __init__(
        self,
        *,
        repository: object | None,
        selection_repository: object | None = None,
        scope_key_for_month: Callable[[str | None], str] | None = None,
    ) -> None:
        self._repository = repository
        self._selection_repository = selection_repository or repository
        self._scope_key_for_month = scope_key_for_month or self._default_scope_key

    def initial_page(
        self,
        month: str | None,
        *,
        paired_query: dict[str, object] | None = None,
        unpaired_query: dict[str, object] | None = None,
    ) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        method = getattr(self._repository, "get_workbench_initial_page", None)
        if not callable(method):
            return self._unavailable(scope_key)
        try:
            payload = method(
                scope_key=scope_key,
                paired_query=paired_query,
                unpaired_query=unpaired_query,
            )
        except (ValueError, WorkbenchPageCursorError) as error:
            return self._bad_request(
                code="invalid_workbench_initial_query",
                message=str(error),
                scope_key=scope_key,
            )
        except WorkbenchDirectQueryUnavailable:
            return self._unavailable(scope_key)
        return WorkbenchQueryResult(HTTPStatus.OK, dict(payload))

    def groups(self, month: str | None, **query: object) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        method = getattr(self._repository, "get_workbench_groups_page", None)
        if not callable(method):
            return self._unavailable(scope_key)
        try:
            payload = method(scope_key=scope_key, **query)
        except (ValueError, WorkbenchPageCursorError) as error:
            return self._bad_request(
                code="invalid_workbench_groups_query",
                message=str(error),
                scope_key=scope_key,
            )
        except WorkbenchDirectQueryUnavailable:
            return self._unavailable(scope_key)
        return WorkbenchQueryResult(HTTPStatus.OK, dict(payload))

    def filter_options(self, month: str | None, **query: object) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        method = getattr(self._repository, "get_workbench_filter_options", None)
        if not callable(method):
            return self._unavailable(scope_key)
        try:
            payload = method(scope_key=scope_key, **query)
        except (ValueError, WorkbenchPageCursorError) as error:
            return self._bad_request(
                code="invalid_workbench_filter_options_query",
                message=str(error),
                scope_key=scope_key,
            )
        except WorkbenchDirectQueryUnavailable:
            return self._unavailable(scope_key)
        return WorkbenchQueryResult(HTTPStatus.OK, dict(payload))

    def group_detail(
        self,
        month: str | None,
        *,
        zone: str,
        group_id: str,
        detail_key: str | None = None,
    ) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        method = getattr(self._repository, "get_workbench_group_detail", None)
        if not callable(method):
            return self._unavailable(scope_key)
        try:
            payload = method(
                scope_key=scope_key,
                zone=zone,
                group_id=group_id,
                detail_key=detail_key,
            )
        except ValueError as error:
            return self._bad_request(
                code="invalid_workbench_group_detail_request",
                message=str(error),
                scope_key=scope_key,
            )
        except WorkbenchDirectQueryUnavailable:
            return self._unavailable(scope_key)
        if not isinstance(payload, dict):
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "workbench_group_not_found",
                    "scope_key": scope_key,
                    "zone": zone,
                    "group_id": group_id,
                },
            )
        return WorkbenchQueryResult(HTTPStatus.OK, dict(payload))

    def row_detail(
        self,
        month: str | None,
        *,
        row_id: str,
        row_type: str | None = None,
    ) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        normalized_row_id = str(row_id or "").strip()
        if not normalized_row_id:
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "workbench_row_not_found",
                    "scope_key": scope_key,
                    "row_id": normalized_row_id,
                },
            )
        method = getattr(self._repository, "get_workbench_row_detail", None)
        if not callable(method):
            return self._unavailable(scope_key)
        try:
            payload = method(
                scope_key=scope_key,
                row_id=normalized_row_id,
                row_type=row_type,
            )
        except ValueError as error:
            return self._bad_request(
                code="invalid_workbench_row_detail_request",
                message=str(error),
                scope_key=scope_key,
            )
        except WorkbenchDirectQueryUnavailable:
            return self._unavailable(scope_key)
        if not isinstance(payload, dict):
            return WorkbenchQueryResult(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "workbench_row_not_found",
                    "scope_key": scope_key,
                    "row_id": normalized_row_id,
                },
            )
        return WorkbenchQueryResult(HTTPStatus.OK, dict(payload))

    def relation_preview_selection(
        self,
        month: str | None,
        *,
        row_ids: list[str],
        row_types: list[str] | None = None,
    ) -> WorkbenchQueryResult:
        scope_key = self._scope_key_for_month(month or "all")
        raw_row_ids = [str(value or "").strip() for value in list(row_ids or [])]
        raw_row_types = [str(value or "").strip().lower() for value in list(row_types or [])]
        if row_types is None:
            return self._bad_request(
                code="invalid_relation_preview_selection",
                message="row_types is required for Workbench relation preview.",
                scope_key=scope_key,
            )
        if len(raw_row_ids) != len(raw_row_types):
            return self._bad_request(
                code="invalid_relation_preview_selection",
                message="row_ids and row_types must have the same length.",
                scope_key=scope_key,
            )
        if any(not row_id for row_id in raw_row_ids):
            return self._bad_request(
                code="invalid_relation_preview_selection",
                message="row_ids must contain non-empty identifiers.",
                scope_key=scope_key,
            )
        normalized_row_types = [
            {
                "oa_application": "oa",
                "bank_transaction": "bank",
                "invoice_record": "invoice",
            }.get(row_type, row_type)
            for row_type in raw_row_types
        ]
        if any(row_type not in {"oa", "bank", "invoice"} for row_type in normalized_row_types):
            return self._bad_request(
                code="invalid_relation_preview_selection",
                message="row_types contains an unsupported canonical row type.",
                scope_key=scope_key,
            )
        identities = list(zip(normalized_row_types, raw_row_ids, strict=True))
        if len(set(identities)) != len(identities):
            return self._bad_request(
                code="invalid_relation_preview_selection",
                message="Workbench relation selection contains a duplicate typed row.",
                scope_key=scope_key,
            )
        normalized_row_ids = raw_row_ids
        if not normalized_row_ids:
            return WorkbenchQueryResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "relation_preview_selection_required",
                    "message": "请至少选择一条工作台记录。",
                    "scope_key": scope_key,
                },
            )
        method = getattr(
            self._selection_repository,
            "get_workbench_relation_preview_selection",
            None,
        )
        if not callable(method):
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "relation_preview_unavailable",
                    "message": "工作台预览暂时不可用，请稍后重试。",
                    "scope_key": scope_key,
                },
            )
        kwargs: dict[str, object] = {
            "scope_key": scope_key,
            "row_ids": normalized_row_ids,
        }
        kwargs["row_types"] = normalized_row_types
        try:
            payload = method(**kwargs)
        except WorkbenchRelationPreviewSelectionError as error:
            return WorkbenchQueryResult(
                HTTPStatus.CONFLICT,
                {"error": error.code, "message": str(error), "scope_key": scope_key},
            )
        except ValueError as error:
            return self._bad_request(
                code="invalid_relation_preview_selection",
                message=str(error),
                scope_key=scope_key,
            )
        except WorkbenchDirectQueryUnavailable:
            return WorkbenchQueryResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "relation_preview_unavailable",
                    "message": "工作台预览暂时不可用，请稍后重试。",
                    "scope_key": scope_key,
                },
            )
        return WorkbenchQueryResult(HTTPStatus.OK, dict(payload))

    @staticmethod
    def _bad_request(
        *,
        code: str,
        message: str,
        scope_key: str,
    ) -> WorkbenchQueryResult:
        return WorkbenchQueryResult(
            HTTPStatus.BAD_REQUEST,
            {"error": code, "message": message, "scope_key": scope_key},
        )

    @staticmethod
    def _unavailable(scope_key: str) -> WorkbenchQueryResult:
        return WorkbenchQueryResult(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "workbench_query_unavailable",
                "message": "工作台查询暂时不可用，请稍后重试。",
                "scope_key": scope_key,
            },
        )

    @staticmethod
    def _default_scope_key(month: str | None) -> str:
        return normalize_workbench_scope_key(month)


__all__ = ["WorkbenchQueryFacade", "WorkbenchQueryResult"]
