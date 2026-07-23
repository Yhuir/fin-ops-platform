from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.postgres_repositories.common import text, text_list
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
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
        expected_source_versions: Callable[[str], dict[str, Any]] | None = None,
        expected_source_versions_by_scope: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
    ) -> None:
        self._read_model_repository = read_model_repository
        self._queue_repository = queue_repository
        self._tenant_id = text(tenant_id) or "default"
        self._expected_source_versions = expected_source_versions
        self._expected_source_versions_by_scope = expected_source_versions_by_scope
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

    def get_batch_accounting_by_row_ids(
        self,
        row_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "batch_accounting_relation_read",
        scope_keys_hint: list[str] | None = None,
        submitted_year: str | None = None,
    ) -> dict[str, Any]:
        normalized_ids = _dedupe_preserve_order(text(value) for value in list(row_ids or []))
        normalized_submitted_year = text(submitted_year) or ""
        annual_scope_keys = _year_scope_keys(normalized_submitted_year)
        if not normalized_ids and not annual_scope_keys:
            result = _facade_result(status=FRESH_WORKBENCH_RELATION_STATUS)
            result["submitted_count"] = 0
            self._last_result = result
            return result
        fallback_scope_keys = _dedupe_preserve_order(
            [*_fallback_scope_keys(scope_keys_hint=scope_keys_hint), *annual_scope_keys]
        )
        reader = getattr(self._read_model_repository, "get_batch_accounting_relation_rows_by_ids", None)
        if not callable(reader):
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=fallback_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable"],
            )
        payload = reader(
            normalized_ids,
            tenant_id=self._tenant_id,
            scope_keys_hint=_fallback_scope_keys(scope_keys_hint=scope_keys_hint),
            submitted_year=normalized_submitted_year or None,
        )
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=fallback_scope_keys,
        )
        if isinstance(payload, dict):
            try:
                result["submitted_count"] = int(payload.get("submitted_count") or 0)
            except (TypeError, ValueError):
                result["submitted_count"] = 0
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
        bulk_reader = getattr(self._read_model_repository, "workbench_relation_scope_summaries", None)
        if callable(bulk_reader) and normalized_month:
            return self.source_versions_for_scopes(
                [normalized_month],
                require_fresh=require_fresh,
                reason=reason,
            )
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

    def source_versions_for_scopes(
        self,
        scope_keys: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_source_versions",
    ) -> dict[str, Any]:
        normalized_scope_keys = _dedupe_preserve_order(
            text(scope_key)
            for scope_key in list(scope_keys or [])
        )
        if not normalized_scope_keys:
            result = _facade_result(status=FRESH_WORKBENCH_RELATION_STATUS)
            self._last_result = result
            return result
        reader = getattr(self._read_model_repository, "workbench_relation_scope_summaries", None)
        if not callable(reader):
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=normalized_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable"],
            )
        payload = reader(
            scope_keys=normalized_scope_keys,
            tenant_id=self._tenant_id,
        )
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=normalized_scope_keys,
        )
        self._last_result = result
        return result

    def list_batch_accounting_relations_by_year(
        self,
        year: str,
        *,
        require_fresh: bool = True,
        reason: str = "batch_accounting_submitted_relations",
    ) -> dict[str, Any]:
        normalized_year = text(year) or ""
        scope_keys = _year_scope_keys(normalized_year)
        reader = getattr(self._read_model_repository, "list_batch_accounting_relation_groups_by_year", None)
        if not callable(reader) or not scope_keys:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(reader) else "year_required"],
            )
        payload = reader(year=normalized_year, tenant_id=self._tenant_id)
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=scope_keys,
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
        scope_source_versions = (
            payload.get("read_model_scope_source_versions")
            if isinstance(payload.get("read_model_scope_source_versions"), dict)
            else {}
        )
        stale_reasons = text_list(payload.get("stale_reasons"))
        canonical_stale_scopes: list[str] = []
        expected_source_versions_by_scope: dict[str, dict[str, Any]] = {}
        if len(scope_keys) > 1 and callable(self._expected_source_versions_by_scope):
            bulk_expected = self._expected_source_versions_by_scope(scope_keys)
            if isinstance(bulk_expected, dict):
                expected_source_versions_by_scope = {
                    scope_key: dict(source_versions)
                    for scope_key, source_versions in bulk_expected.items()
                    if isinstance(source_versions, dict)
                }
        if callable(self._expected_source_versions) or callable(self._expected_source_versions_by_scope):
            for scope_key in scope_keys:
                expected_source_versions = expected_source_versions_by_scope.get(scope_key)
                if expected_source_versions is None and callable(self._expected_source_versions):
                    expected_source_versions = self._expected_source_versions(scope_key)
                expected = require_expected_source_versions(
                    expected_source_versions,
                    context="workbench_relation_read",
                )
                actual = scope_source_versions.get(scope_key)
                if not isinstance(actual, dict) and len(scope_keys) == 1:
                    actual = source_versions
                mismatch_reasons = source_version_mismatch_reasons(
                    expected=expected,
                    actual=actual if isinstance(actual, dict) else {},
                )
                if mismatch_reasons:
                    canonical_stale_scopes.append(scope_key)
                    stale_reasons.extend(
                        f"{scope_key}:{reason}"
                        for reason in mismatch_reasons
                        if f"{scope_key}:{reason}" not in stale_reasons
                    )
        if canonical_stale_scopes:
            status = "stale"
        if require_fresh and status != FRESH_WORKBENCH_RELATION_STATUS:
            refresh_scope_keys = canonical_stale_scopes or scope_keys
            refresh_enqueued = self._enqueue_scope_refresh(scope_keys=refresh_scope_keys, reason=reason)
            return _facade_result(
                status=status,
                rows=[],
                groups=[],
                source_versions=source_versions,
                scope_source_versions=scope_source_versions,
                scope_keys=scope_keys,
                refresh_enqueued=refresh_enqueued,
                stale_reasons=stale_reasons,
            )
        return _facade_result(
            status=status,
            rows=[row for row in list(payload.get("rows") or []) if isinstance(row, dict)],
            groups=[group for group in list(payload.get("groups") or []) if isinstance(group, dict)],
            source_versions=source_versions,
            scope_source_versions=scope_source_versions,
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
    scope_source_versions: dict[str, Any] | None = None,
    scope_keys: list[str] | None = None,
    refresh_enqueued: bool = False,
    stale_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": _facade_status(status),
        "rows": list(rows or []),
        "groups": list(groups or []),
        "source_versions": dict(source_versions or {}),
        "read_model_scope_source_versions": dict(scope_source_versions or {}),
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


def _year_scope_keys(year: str) -> list[str]:
    normalized_year = text(year) or ""
    if len(normalized_year) == 4 and normalized_year.isdigit():
        return [f"{normalized_year}-{month:02d}" for month in range(1, 13)]
    return []


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
