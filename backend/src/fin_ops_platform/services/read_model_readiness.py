from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from fin_ops_platform.services.app_status_read_model_registry import (
    APP_STATUS_READ_MODEL_REGISTRY,
    read_model_by_refresh_event_type,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


READINESS_WRITE_STATUSES = {"fresh", "refreshing", "failed", "schema_mismatch", "source_mismatch", "unavailable"}


class ReadModelReadinessReporter:
    def __init__(
        self,
        *,
        readiness_repository: Any,
        registry: dict[str, Any] = APP_STATUS_READ_MODEL_REGISTRY,
        clock: Callable[[], object] | None = None,
    ) -> None:
        self._readiness_repository = readiness_repository
        self._registry = registry
        self._by_event_type = read_model_by_refresh_event_type()
        self._clock = clock or (lambda: datetime.now(UTC))

    def wrap_handler(self, handler: Callable[[RuntimeQueueEvent], dict[str, Any]]) -> Callable[[RuntimeQueueEvent], dict[str, Any]]:
        def wrapped(event: RuntimeQueueEvent) -> dict[str, Any]:
            try:
                result = handler(event)
            except Exception as exc:
                self.record_event_failure(event, exc)
                raise
            self.record_event_success(event, result)
            return result

        return wrapped

    def record_event_success(self, event: RuntimeQueueEvent, result: dict[str, Any] | None) -> None:
        payload = result if isinstance(result, dict) else {}
        if payload.get("skipped"):
            return
        if payload.get("enqueued_scope_keys") and not str(payload.get("readiness_status") or "").strip():
            return
        definition = self._definition_for_event(event)
        scope_key = str(payload.get("scope_key") or event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if not scope_key:
            return
        readiness_status = str(payload.get("readiness_status") or "").strip().lower()
        if readiness_status and readiness_status != "fresh":
            if readiness_status not in READINESS_WRITE_STATUSES:
                raise ValueError(f"Unsupported readiness status: {readiness_status!r}.")
            self._record(
                read_model_key=definition.key,
                scope_key=scope_key,
                tenant_id=event.tenant_id,
                status=readiness_status,
                schema_version=self._schema_version(definition.key, payload),
                source_versions=self._source_versions(event, payload),
                row_count=self._row_count(payload),
                generated_at=payload.get("generated_at") or self._clock(),
                last_error=str(payload.get("last_error") or payload.get("message") or ""),
                raw_payload=payload,
            )
            return
        self.record_fresh(
            read_model_key=definition.key,
            scope_key=scope_key,
            tenant_id=event.tenant_id,
            schema_version=self._schema_version(definition.key, payload),
            source_versions=self._source_versions(event, payload),
            row_count=self._row_count(payload),
            generated_at=payload.get("generated_at") or self._clock(),
            raw_payload=payload,
        )

    def record_event_failure(self, event: RuntimeQueueEvent, error: BaseException) -> None:
        definition = self._definition_for_event(event)
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "all").strip() or "all"
        self.record_failed(
            read_model_key=definition.key,
            scope_key=scope_key,
            tenant_id=event.tenant_id,
            error=error,
            source_versions=self._source_versions(event, {}),
        )

    def record_fresh(
        self,
        *,
        read_model_key: str,
        scope_key: str,
        tenant_id: str = "default",
        schema_version: object = "",
        source_versions: dict[str, Any] | None = None,
        row_count: int | None = None,
        generated_at: object | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        self._record(
            read_model_key=read_model_key,
            scope_key=scope_key,
            tenant_id=tenant_id,
            status="fresh",
            schema_version=schema_version,
            source_versions=source_versions or {},
            row_count=row_count,
            generated_at=generated_at or self._clock(),
            raw_payload=raw_payload or {},
        )

    def record_failed(
        self,
        *,
        read_model_key: str,
        scope_key: str,
        tenant_id: str = "default",
        error: BaseException | str,
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        last_error = str(error)
        if not last_error and isinstance(error, BaseException):
            last_error = error.__class__.__name__
        self._record(
            read_model_key=read_model_key,
            scope_key=scope_key,
            tenant_id=tenant_id,
            status="failed",
            source_versions=source_versions or {},
            last_error=last_error,
        )

    def record_schema_mismatch(self, *, read_model_key: str, scope_key: str, tenant_id: str = "default", error: str = "") -> None:
        self._record(read_model_key=read_model_key, scope_key=scope_key, tenant_id=tenant_id, status="schema_mismatch", last_error=error)

    def record_source_mismatch(self, *, read_model_key: str, scope_key: str, tenant_id: str = "default", error: str = "") -> None:
        self._record(read_model_key=read_model_key, scope_key=scope_key, tenant_id=tenant_id, status="source_mismatch", last_error=error)

    def record_unavailable(self, *, read_model_key: str, scope_key: str, tenant_id: str = "default", error: str = "") -> None:
        self._record(read_model_key=read_model_key, scope_key=scope_key, tenant_id=tenant_id, status="unavailable", last_error=error)

    def _record(
        self,
        *,
        read_model_key: str,
        scope_key: str,
        tenant_id: str = "default",
        status: str,
        schema_version: object = "",
        source_versions: dict[str, Any] | None = None,
        row_count: int | None = None,
        generated_at: object | None = None,
        last_error: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        definition = self._definition_for_key(read_model_key)
        if status not in READINESS_WRITE_STATUSES:
            raise ValueError(f"Unsupported readiness status: {status!r}.")
        record = getattr(self._readiness_repository, "record_read_model_readiness", None)
        if not callable(record):
            raise RuntimeError("readiness_repository must expose record_read_model_readiness.")
        record(
            tenant_id=tenant_id or "default",
            read_model_key=definition.key,
            scope_type=definition.scope_type,
            scope_key=str(scope_key or "").strip() or "all",
            status=status,
            schema_version=str(schema_version or ""),
            source_versions=source_versions or {},
            row_count=row_count,
            generated_at=generated_at,
            last_error=last_error,
            raw_payload=raw_payload or {},
        )

    def _definition_for_event(self, event: RuntimeQueueEvent) -> Any:
        definition = self._by_event_type.get(event.event_type)
        if definition is None:
            raise ValueError(f"Unregistered app status read model event type: {event.event_type!r}.")
        return definition

    def _definition_for_key(self, read_model_key: str) -> Any:
        key = str(read_model_key or "").strip()
        definition = self._registry.get(key)
        if definition is None:
            raise ValueError(f"Unregistered app status read model: {read_model_key!r}.")
        return definition

    @staticmethod
    def _row_count(payload: dict[str, Any]) -> int | None:
        for key in ("row_count", "entry_count", "bank_row_count", "batch_count"):
            if key not in payload:
                continue
            try:
                return max(0, int(payload.get(key) or 0))
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _source_versions(event: RuntimeQueueEvent, payload: dict[str, Any]) -> dict[str, Any]:
        source_versions = payload.get("source_versions")
        if isinstance(source_versions, dict):
            return dict(source_versions)
        if event.source_version is not None:
            return {"source_version": event.source_version}
        payload_source_version = event.payload.get("source_version")
        if payload_source_version is not None:
            return {"source_version": payload_source_version}
        return {}

    @staticmethod
    def _schema_version(read_model_key: str, payload: dict[str, Any]) -> str:
        if payload.get("schema_version") is not None:
            return str(payload.get("schema_version") or "")
        source_versions = payload.get("source_versions")
        if isinstance(source_versions, dict):
            for key in (
                f"{read_model_key}_schema_version",
                f"{read_model_key}_read_model_schema_version",
                "schema_version",
            ):
                if source_versions.get(key) is not None:
                    return str(source_versions.get(key) or "")
        return ""
