from __future__ import annotations

from typing import Any

from fin_ops_platform.services.invoice_lifecycle_read_model_repository import InvoiceLifecycleReadModelRepositoryPort
from fin_ops_platform.services.postgres_repositories.common import text
from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


FRESH_INVOICE_LIFECYCLE_STATUS = "fresh"
NON_FRESH_INVOICE_LIFECYCLE_STATUSES = {"refreshing", "stale", "missing", "schema_mismatch", "unavailable", "failed"}
INVOICE_LIFECYCLE_SCOPE_TYPE = "invoice_lifecycle"
INVOICE_LIFECYCLE_READ_DEPENDENCIES = READ_MODEL_MANIFEST[INVOICE_LIFECYCLE_SCOPE_TYPE].read_dependencies


class InvoiceLifecycleReadFacade:
    """Freshness-gated read boundary for normalized invoice lifecycle decisions."""

    def __init__(
        self,
        *,
        read_model_repository: Any,
        queue_repository: Any | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._read_model_repository_source = read_model_repository
        self._read_model_repository = InvoiceLifecycleReadModelRepositoryPort(read_model_repository)
        self._queue_repository = queue_repository
        self._tenant_id = text(tenant_id) or "default"
        self._last_result: dict[str, Any] = _facade_result(status="missing")

    @property
    def last_source_versions(self) -> dict[str, Any]:
        source_versions = self._last_result.get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def get_by_subject_ids(
        self,
        subject_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_invoice_lifecycle_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_ids = _dedupe_preserve_order(text(value) for value in list(subject_ids or []))
        if not normalized_ids:
            result = _facade_result(status=FRESH_INVOICE_LIFECYCLE_STATUS)
            self._last_result = result
            return result
        reader = getattr(self._read_model_repository, "get_invoice_lifecycle_rows_by_subject_ids", None)
        fallback_scope_keys = _fallback_scope_keys(month_hint=month_hint, scope_keys_hint=scope_keys_hint)
        if not callable(getattr(self._read_model_repository_source, "get_invoice_lifecycle_rows_by_subject_ids", None)):
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=fallback_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable"],
            )
        payload = reader(normalized_ids, tenant_id=self._tenant_id)
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=fallback_scope_keys,
        )
        self._last_result = result
        return result

    def get_by_invoice_identity_keys(
        self,
        invoice_identity_keys: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_invoice_lifecycle_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_keys = _dedupe_preserve_order(text(value) for value in list(invoice_identity_keys or []))
        if not normalized_keys:
            result = _facade_result(status=FRESH_INVOICE_LIFECYCLE_STATUS)
            self._last_result = result
            return result
        reader = getattr(self._read_model_repository, "get_invoice_lifecycle_rows_by_identity_keys", None)
        fallback_scope_keys = _fallback_scope_keys(month_hint=month_hint, scope_keys_hint=scope_keys_hint)
        if not callable(getattr(self._read_model_repository_source, "get_invoice_lifecycle_rows_by_identity_keys", None)):
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=fallback_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable"],
            )
        payload = reader(normalized_keys, tenant_id=self._tenant_id)
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
        subject_types: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_invoice_lifecycle_read",
    ) -> dict[str, Any]:
        normalized_month = text(month)
        reader = getattr(self._read_model_repository, "list_invoice_lifecycle_rows", None)
        source_reader = getattr(self._read_model_repository_source, "list_invoice_lifecycle_rows", None)
        if not callable(source_reader) or not normalized_month:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=[normalized_month] if normalized_month else [],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(source_reader) else "month_required"],
            )
        payload = reader(
            month=normalized_month,
            subject_types=_dedupe_preserve_order(text(value) for value in list(subject_types or [])),
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
        scope_keys = _text_list(payload.get("read_model_scope_keys")) or list(fallback_scope_keys)
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        stale_reasons = _text_list(payload.get("stale_reasons"))
        if require_fresh and status != FRESH_INVOICE_LIFECYCLE_STATUS:
            refresh_enqueued = self._enqueue_scope_refresh(scope_keys=scope_keys or ["all"], reason=reason)
            return _facade_result(
                status=status,
                rows=[],
                source_versions=source_versions,
                scope_keys=scope_keys,
                refresh_enqueued=refresh_enqueued,
                stale_reasons=stale_reasons,
            )
        return _facade_result(
            status=status,
            rows=[row for row in list(payload.get("rows") or []) if isinstance(row, dict)],
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
        normalized_scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys or []))
        refresh_enqueued = (
            self._enqueue_scope_refresh(scope_keys=normalized_scope_keys or ["all"], reason=reason)
            if require_fresh
            else False
        )
        result = _facade_result(
            status=_facade_status(status),
            rows=[],
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
        normalized_scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys or []))
        dependency_enqueued = False
        for dependency_scope_type, dependency_scope_key in _invoice_lifecycle_dependency_scopes(normalized_scope_keys):
            if self._dependency_scope_is_fresh(dependency_scope_type, dependency_scope_key):
                continue
            dependency_enqueued = bool(
                refresh_gateway.enqueue_one(
                    dependency_scope_type,
                    dependency_scope_key,
                    reason="invoice_lifecycle_access_dependency",
                    tenant_id=self._tenant_id,
                    priority="high",
                )
            ) or dependency_enqueued
        lifecycle_enqueued = bool(
            refresh_gateway.enqueue_many(
                INVOICE_LIFECYCLE_SCOPE_TYPE,
                normalized_scope_keys,
                reason=reason,
                tenant_id=self._tenant_id,
                priority="high",
            )
        )
        return dependency_enqueued or lifecycle_enqueued

    def _dependency_scope_is_fresh(self, scope_type: str, scope_key: str) -> bool:
        checker = getattr(self._queue_repository, "read_model_refresh_is_fresh", None)
        if not callable(checker):
            return False
        return bool(
            checker(
                tenant_id=self._tenant_id,
                scope_type=scope_type,
                scope_key=scope_key,
            )
        )


def _facade_result(
    *,
    status: str,
    rows: list[dict[str, Any]] | None = None,
    source_versions: dict[str, Any] | None = None,
    scope_keys: list[str] | None = None,
    refresh_enqueued: bool = False,
    stale_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": _facade_status(status),
        "rows": list(rows or []),
        "source_versions": dict(source_versions or {}),
        "read_model_scope_keys": list(scope_keys or []),
        "refresh_enqueued": bool(refresh_enqueued),
        "stale_reasons": list(stale_reasons or []),
    }


def _facade_status(value: object) -> str:
    normalized = text(value) or FRESH_INVOICE_LIFECYCLE_STATUS
    if normalized == FRESH_INVOICE_LIFECYCLE_STATUS:
        return normalized
    if normalized in NON_FRESH_INVOICE_LIFECYCLE_STATUSES:
        return normalized
    return "stale"


def _fallback_scope_keys(*, month_hint: str | None = None, scope_keys_hint: list[str] | None = None) -> list[str]:
    scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys_hint or []))
    if scope_keys:
        return scope_keys
    month = text(month_hint)
    return [month] if month else []


def _invoice_lifecycle_dependency_scopes(scope_keys: list[str]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for scope_key in scope_keys:
        if len(scope_key) != 7 or scope_key[4:5] != "-" or not scope_key[:4].isdigit() or not scope_key[5:].isdigit():
            continue
        for dependency in INVOICE_LIFECYCLE_READ_DEPENDENCIES:
            if dependency == "pending_invoice":
                targets.extend(
                    [
                        (dependency, f"expense:all:{scope_key}"),
                        (dependency, f"income:all:{scope_key}"),
                    ]
                )
                continue
            targets.append((dependency, scope_key))
    return list(dict.fromkeys(targets))


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe_preserve_order(text(item) for item in value)


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
