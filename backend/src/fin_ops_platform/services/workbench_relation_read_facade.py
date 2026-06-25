from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import text, text_list
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


FRESH_WORKBENCH_RELATION_STATUS = "fresh"
NON_FRESH_WORKBENCH_RELATION_STATUSES = {"refreshing", "stale", "missing", "schema_mismatch", "unavailable"}
WORKBENCH_RELATION_SCOPE_TYPE = "workbench_relation"


class WorkbenchRelationReadFacade:
    """Freshness-gated read boundary for OA/bank/invoice relation context.

    This facade deliberately returns a generic relation context instead of a page
    display DTO. Downstream read-model workers can consume the same facts without
    repeating pair-relation joins or OA attachment invoice handling.
    """

    def __init__(
        self,
        *,
        read_model_repository: Any,
        queue_repository: Any | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._read_model_repository = read_model_repository
        self._queue_repository = queue_repository
        self._tenant_id = text(tenant_id) or "default"
        self._last_result: dict[str, Any] = _facade_result(status="missing")

    @property
    def last_source_versions(self) -> dict[str, Any]:
        source_versions = self._last_result.get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def get_by_row_ids(
        self,
        row_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_ids = _dedupe_preserve_order(text(value) for value in list(row_ids or []))
        if not normalized_ids:
            result = _facade_result(status=FRESH_WORKBENCH_RELATION_STATUS)
            self._last_result = result
            return result
        reader = getattr(self._read_model_repository, "get_workbench_relation_rows_by_ids", None)
        fallback_scope_keys = _fallback_scope_keys(month_hint=month_hint, scope_keys_hint=scope_keys_hint)
        if not callable(reader):
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=fallback_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable"],
            )
        payload = reader(normalized_ids, tenant_id=self._tenant_id, scope_keys_hint=fallback_scope_keys)
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=fallback_scope_keys,
        )
        self._last_result = result
        return result

    def list_by_month(
        self,
        month: str,
        *,
        row_types: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_read",
    ) -> dict[str, Any]:
        normalized_month = text(month) or ""
        reader = getattr(self._read_model_repository, "list_workbench_relation_rows", None)
        if not callable(reader) or not normalized_month:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=[normalized_month] if normalized_month else [],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(reader) else "month_required"],
            )
        payload = reader(
            month=normalized_month,
            row_types=_dedupe_preserve_order(text(value) for value in list(row_types or [])),
            relation_status=None,
            tenant_id=self._tenant_id,
        )
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=[normalized_month],
        )
        self._last_result = result
        return result

    def source_versions_for_month(
        self,
        month: str,
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_source_versions",
    ) -> dict[str, Any]:
        normalized_month = text(month) or ""
        reader = getattr(self._read_model_repository, "workbench_relation_source_versions", None)
        if not callable(reader) or not normalized_month:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=[normalized_month] if normalized_month else [],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(reader) else "month_required"],
            )
        source_versions = reader(scope_key=normalized_month, tenant_id=self._tenant_id)
        payload = {
            "read_model_status": FRESH_WORKBENCH_RELATION_STATUS if isinstance(source_versions, dict) and source_versions else "missing",
            "rows": [],
            "groups": [],
            "source_versions": dict(source_versions) if isinstance(source_versions, dict) else {},
            "read_model_scope_keys": [normalized_month],
            "stale_reasons": [],
        }
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=[normalized_month],
        )
        self._last_result = result
        return result

    def list_unlinked(
        self,
        month: str,
        *,
        row_types: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_unlinked_read",
    ) -> dict[str, Any]:
        normalized_month = text(month) or ""
        reader = getattr(self._read_model_repository, "list_workbench_relation_rows", None)
        if not callable(reader) or not normalized_month:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=[normalized_month] if normalized_month else [],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(reader) else "month_required"],
            )
        payload = reader(
            month=normalized_month,
            row_types=_dedupe_preserve_order(text(value) for value in list(row_types or [])),
            relation_status="unlinked",
            tenant_id=self._tenant_id,
        )
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=[normalized_month],
        )
        self._last_result = result
        return result

    def relation_groups_by_ids(
        self,
        group_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_group_read",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_ids = _dedupe_preserve_order(text(value) for value in list(group_ids or []))
        if not normalized_ids:
            result = _facade_result(status=FRESH_WORKBENCH_RELATION_STATUS)
            self._last_result = result
            return result
        reader = getattr(self._read_model_repository, "get_workbench_relation_groups_by_ids", None)
        fallback_scope_keys = _fallback_scope_keys(scope_keys_hint=scope_keys_hint)
        if not callable(reader):
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=fallback_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable"],
            )
        payload = reader(normalized_ids, tenant_id=self._tenant_id, scope_keys_hint=fallback_scope_keys)
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=fallback_scope_keys,
        )
        self._last_result = result
        return result

    def _result_from_repository_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        require_fresh: bool,
        reason: str,
        fallback_scope_keys: list[str],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return self._non_fresh_result(
                status="missing",
                scope_keys=fallback_scope_keys or ["all"],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["read_model_missing"],
            )
        status = _facade_status(payload.get("read_model_status"))
        scope_keys = text_list(payload.get("read_model_scope_keys")) or list(fallback_scope_keys)
        if require_fresh and status != FRESH_WORKBENCH_RELATION_STATUS and not scope_keys:
            scope_keys = ["all"]
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        stale_reasons = text_list(payload.get("stale_reasons"))
        if require_fresh and status != FRESH_WORKBENCH_RELATION_STATUS:
            refresh_enqueued = self._enqueue_scope_refresh(scope_keys=scope_keys, reason=reason)
            return _facade_result(
                status=status,
                rows=[],
                groups=[],
                source_versions=source_versions,
                scope_keys=scope_keys,
                refresh_enqueued=refresh_enqueued,
                stale_reasons=stale_reasons,
            )
        return _facade_result(
            status=status,
            rows=[row for row in list(payload.get("rows") or []) if isinstance(row, dict)],
            groups=[group for group in list(payload.get("groups") or []) if isinstance(group, dict)],
            source_versions=source_versions,
            scope_keys=scope_keys,
            refresh_enqueued=False,
            stale_reasons=stale_reasons,
        )

    def _non_fresh_result(
        self,
        *,
        status: str,
        scope_keys: list[str],
        require_fresh: bool,
        reason: str,
        stale_reasons: list[str],
    ) -> dict[str, Any]:
        normalized_status = _facade_status(status)
        normalized_scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys or []))
        refresh_enqueued = (
            self._enqueue_scope_refresh(scope_keys=normalized_scope_keys or ["all"], reason=reason)
            if require_fresh
            else False
        )
        result = _facade_result(
            status=normalized_status,
            rows=[],
            groups=[],
            source_versions={},
            scope_keys=normalized_scope_keys,
            refresh_enqueued=refresh_enqueued,
            stale_reasons=stale_reasons,
        )
        self._last_result = result
        return result

    def _enqueue_scope_refresh(self, *, scope_keys: list[str], reason: str) -> bool:
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return False
        return bool(
            refresh_gateway.enqueue_many(
                WORKBENCH_RELATION_SCOPE_TYPE,
                _dedupe_preserve_order(text(value) for value in list(scope_keys or [])),
                reason=reason,
            )
        )


def _facade_result(
    *,
    status: str,
    rows: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
    source_versions: dict[str, Any] | None = None,
    scope_keys: list[str] | None = None,
    refresh_enqueued: bool = False,
    stale_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": _facade_status(status),
        "rows": list(rows or []),
        "groups": list(groups or []),
        "source_versions": dict(source_versions or {}),
        "read_model_scope_keys": list(scope_keys or []),
        "refresh_enqueued": bool(refresh_enqueued),
        "stale_reasons": list(stale_reasons or []),
    }


def _facade_status(value: object) -> str:
    normalized = text(value) or FRESH_WORKBENCH_RELATION_STATUS
    if normalized == FRESH_WORKBENCH_RELATION_STATUS:
        return normalized
    if normalized in NON_FRESH_WORKBENCH_RELATION_STATUSES:
        return normalized
    return "stale"


def _fallback_scope_keys(*, month_hint: str | None = None, scope_keys_hint: list[str] | None = None) -> list[str]:
    scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys_hint or []))
    if scope_keys:
        return scope_keys
    month = text(month_hint)
    return [month] if month else []


def _dedupe_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
