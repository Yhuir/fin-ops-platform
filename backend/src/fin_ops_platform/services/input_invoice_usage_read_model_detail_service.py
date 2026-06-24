from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    input_invoice_usage_relation_details_from_row,
)
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)


SourceVersionsProvider = Callable[..., dict[str, object]]


class InputInvoiceUsageReadModelDetailService:
    def __init__(
        self,
        *,
        repository: Any,
        enqueue_refresh: Callable[[str, str], bool],
        source_versions_provider: SourceVersionsProvider,
    ) -> None:
        self._repository = repository
        self._enqueue_refresh = enqueue_refresh
        self._source_versions_provider = source_versions_provider

    def relation_details(self, row_id: str, *, kind: str) -> dict[str, object] | None:
        normalized_kind = str(kind or "").strip()
        if normalized_kind not in {"oa", "bank", "invoice"}:
            raise InputInvoiceUsageError("invalid_relation_kind", "kind must be oa, bank or invoice.")
        lookup = getattr(self._repository, "get_input_invoice_usage_row_by_row_id", None)
        if not callable(lookup):
            return None
        try:
            payload = lookup(row_id)
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_input_invoice_usage_query", str(exc)) from exc
        if not isinstance(payload, dict):
            self._enqueue_refresh("all", "api_detail_miss")
            return self.refreshing_payload(kind=normalized_kind, scope_key="all")
        scope_key = str(payload.get("read_model_scope_key") or "all")
        refresh_status = str(payload.get("refresh_status") or "fresh")
        if refresh_status != "fresh":
            self._enqueue_refresh(scope_key, "api_detail_stale")
            return self.refreshing_payload(kind=normalized_kind, scope_key=scope_key)
        stale_reasons = source_version_mismatch_reasons(
            expected=require_expected_source_versions(
                _source_versions_from_provider(self._source_versions_provider, scope_key=scope_key),
                context="input_invoice_usage_read_model_detail",
            ),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            self._enqueue_refresh(scope_key, "api_detail_source_versions_stale")
            return self.refreshing_payload(kind=normalized_kind, scope_key=scope_key, stale_reasons=stale_reasons)
        row = payload.get("row")
        if not isinstance(row, dict):
            raise InputInvoiceUsageError(
                "row_not_found",
                f"Input invoice usage row not found: {row_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        try:
            result = input_invoice_usage_relation_details_from_row(row, kind=normalized_kind)
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_relation_kind", str(exc)) from exc
        result["read_model_status"] = "fresh"
        result["readModelStatus"] = "fresh"
        result["read_model_scope_key"] = scope_key
        return result

    @staticmethod
    def refreshing_payload(
        *,
        kind: str,
        scope_key: str,
        stale_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        title = {
            "oa": "OA关联明细",
            "bank": "银行流水关联明细",
            "invoice": "发票关联明细",
        }.get(str(kind or "").strip(), "关联明细")
        payload: dict[str, object] = {
            "title": title,
            "detailAvailable": False,
            "unavailableReason": "详情数据正在刷新，请稍后重试。",
            "sections": [],
            "read_model_status": "refreshing",
            "readModelStatus": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload


def _source_versions_from_provider(
    provider: SourceVersionsProvider,
    *,
    scope_key: str | None,
) -> dict[str, object]:
    try:
        return dict(provider(scope_key=scope_key) or {})
    except TypeError:
        return dict(provider() or {})
