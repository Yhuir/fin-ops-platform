from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable


@dataclass(frozen=True)
class WorkbenchLegacyApiSqlReadResult:
    status_code: HTTPStatus
    payload: dict[str, object]


class WorkbenchLegacyApiSqlReadProvider:
    """Read-only provider for legacy /api/workbench SQL read-model payloads."""

    def __init__(
        self,
        *,
        repository_provider: Callable[[], object | None],
        scope_key_for_month: Callable[[str], str],
        enqueue_workbench_refresh: Callable[..., None],
        stale_reasons: Callable[..., list[str]],
        oa_sync_refresh_reason: Callable[[dict[str, object]], str | None],
        enqueue_oa_projection_sync: Callable[..., None],
        current_oa_attachment_invoice_parser_version: Callable[[], str | None],
        current_oa_projection_sync_version: Callable[[], str | None],
    ) -> None:
        self._repository_provider = repository_provider
        self._scope_key_for_month = scope_key_for_month
        self._enqueue_workbench_refresh = enqueue_workbench_refresh
        self._stale_reasons = stale_reasons
        self._oa_sync_refresh_reason = oa_sync_refresh_reason
        self._enqueue_oa_projection_sync = enqueue_oa_projection_sync
        self._current_oa_attachment_invoice_parser_version = current_oa_attachment_invoice_parser_version
        self._current_oa_projection_sync_version = current_oa_projection_sync_version

    def read(
        self,
        month: str,
        *,
        page: str | None = None,
        page_size: str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
    ) -> WorkbenchLegacyApiSqlReadResult | None:
        repository = self._repository_provider()
        get_view = getattr(repository, "get_workbench_view", None)
        if not callable(get_view):
            return None
        scope_key = self._scope_key_for_month(month)
        view = get_view(
            scope_key=scope_key,
            page=page,
            page_size=page_size,
            status=status,
            source_kind=source_kind,
            search=search,
        )
        if not isinstance(view, dict):
            self._enqueue_workbench_refresh(scope_key, reason="api_miss")
            return WorkbenchLegacyApiSqlReadResult(
                HTTPStatus.ACCEPTED,
                {
                    "read_model_status": "refreshing",
                    "scope_key": scope_key,
                    "message": "Workbench read model is missing; refresh has been enqueued.",
                },
            )
        payload = dict(view.get("payload") if isinstance(view.get("payload"), dict) else {})
        oa_sync_refresh_reason = self._oa_sync_refresh_reason(view)
        if oa_sync_refresh_reason:
            self._enqueue_oa_projection_sync(
                scope_key,
                reason=oa_sync_refresh_reason,
            )
            payload["read_model_status"] = "refreshing"
            payload["read_model_scope_key"] = scope_key
            payload["read_model_refresh_reason"] = oa_sync_refresh_reason
            current_parser_version = self._current_oa_attachment_invoice_parser_version()
            if current_parser_version:
                payload["oa_attachment_invoice_parser_version"] = current_parser_version
            current_projection_version = self._current_oa_projection_sync_version()
            if current_projection_version:
                payload["oa_projection_sync_version"] = current_projection_version
            self._copy_read_model_metadata(view, payload)
            return WorkbenchLegacyApiSqlReadResult(HTTPStatus.ACCEPTED, payload)

        refresh_status = str(view.get("refresh_status") or view.get("cache_status") or "fresh")
        stale_reasons = self._stale_reasons(
            view.get("source_versions"),
            scope_key=scope_key,
        )
        if stale_reasons:
            refresh_status = "stale"
            payload["read_model_stale_reasons"] = stale_reasons
        if refresh_status != "fresh":
            self._enqueue_workbench_refresh(scope_key, reason="api_stale")
        payload["read_model_status"] = refresh_status
        payload["read_model_scope_key"] = scope_key
        self._copy_read_model_metadata(view, payload)
        return WorkbenchLegacyApiSqlReadResult(HTTPStatus.OK, payload)

    @staticmethod
    def _copy_read_model_metadata(view: dict[str, object], payload: dict[str, object]) -> None:
        if view.get("generated_at"):
            payload["read_model_generated_at"] = view.get("generated_at")
        if isinstance(view.get("rows_page"), dict):
            payload["rows_page"] = view.get("rows_page")
