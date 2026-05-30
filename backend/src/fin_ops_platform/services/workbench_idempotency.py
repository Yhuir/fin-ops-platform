from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "jwt",
}
_FINGERPRINT_EXCLUDED_KEYS = {
    "headers",
    "request_headers",
    "trace_id",
    "x_trace_id",
    "x_request_id",
    "request_id",
    "request_started_at",
    "request_timestamp",
    "timestamp",
    "created_at",
    "updated_at",
}
_STATUS_VALUES = {"reserved", "committed", "failed"}


@dataclass(frozen=True)
class WorkbenchIdempotencyRecord:
    tenant_id: str
    actor_id: str
    action_name: str
    idempotency_key: str
    request_fingerprint: str
    status: str
    request_payload: dict[str, Any] = field(default_factory=dict)
    response_payload: dict[str, Any] = field(default_factory=dict)
    source_versions: dict[str, Any] = field(default_factory=dict)
    outbox_event_ids: list[Any] = field(default_factory=list)
    created_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.status not in _STATUS_VALUES:
            raise ValueError(f"Workbench idempotency status must be one of {sorted(_STATUS_VALUES)}.")

    @property
    def unique_identity(self) -> tuple[str, str, str]:
        return (self.tenant_id, self.actor_id, self.idempotency_key)

    @property
    def action_identity(self) -> tuple[str, str, str]:
        return (self.tenant_id, self.action_name, self.idempotency_key)

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.action_identity

    def to_storage_payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "action_name": self.action_name,
            "idempotency_key": self.idempotency_key,
            "request_fingerprint": self.request_fingerprint,
            "status": self.status,
            "request_payload": _sanitize_payload(self.request_payload),
            "response_payload": _sanitize_payload(self.response_payload),
            "source_versions": _sanitize_payload(self.source_versions),
            "outbox_event_ids": _sanitize_payload(self.outbox_event_ids),
            "created_at": _datetime_to_storage(self.created_at),
            "completed_at": _datetime_to_storage(self.completed_at),
            "expires_at": _datetime_to_storage(self.expires_at),
        }


class WorkbenchIdempotencyKeyConflict(ValueError):
    status_code = 409

    def __init__(
        self,
        *,
        idempotency_key: str,
        existing_fingerprint: str,
        incoming_fingerprint: str,
        action_name: str,
    ) -> None:
        super().__init__("same idempotency key was used with a different Workbench request fingerprint")
        self.idempotency_key = idempotency_key
        self.existing_fingerprint = existing_fingerprint
        self.incoming_fingerprint = incoming_fingerprint
        self.action_name = action_name

    def to_response_payload(self) -> dict[str, Any]:
        return {
            "success": False,
            "error": "idempotency_key_conflict",
            "idempotency_key": self.idempotency_key,
            "action_name": self.action_name,
            "message": "The same idempotency key was used with a different Workbench request payload.",
        }


class InMemoryWorkbenchIdempotencyRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], WorkbenchIdempotencyRecord] = {}

    def get_committed_or_reserved(
        self,
        tenant_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkbenchIdempotencyRecord | None:
        return self._records.get((tenant_id, actor_id, idempotency_key))

    def reserve(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action_name: str,
        idempotency_key: str,
        request_fingerprint: str,
        request_payload: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> WorkbenchIdempotencyRecord:
        record = WorkbenchIdempotencyRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="reserved",
            request_payload=request_payload or {},
            created_at=_utcnow(),
            expires_at=expires_at,
        )
        self._records[record.unique_identity] = record
        return record

    def commit(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action_name: str,
        idempotency_key: str,
        request_fingerprint: str,
        response_payload: dict[str, Any],
        source_versions: dict[str, Any] | None = None,
        outbox_event_ids: list[Any] | None = None,
    ) -> WorkbenchIdempotencyRecord:
        identity = (tenant_id, actor_id, idempotency_key)
        existing = self._records.get(identity)
        record = WorkbenchIdempotencyRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="committed",
            request_payload=existing.request_payload if existing is not None else {},
            response_payload=response_payload,
            source_versions=source_versions or {},
            outbox_event_ids=outbox_event_ids or [],
            created_at=existing.created_at if existing is not None else _utcnow(),
            completed_at=_utcnow(),
            expires_at=existing.expires_at if existing is not None else None,
        )
        self._records[identity] = record
        return record

    def mark_failed(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action_name: str,
        idempotency_key: str,
        request_fingerprint: str,
        response_payload: dict[str, Any] | None = None,
    ) -> WorkbenchIdempotencyRecord:
        identity = (tenant_id, actor_id, idempotency_key)
        existing = self._records.get(identity)
        record = WorkbenchIdempotencyRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="failed",
            request_payload=existing.request_payload if existing is not None else {},
            response_payload=response_payload or {},
            created_at=existing.created_at if existing is not None else _utcnow(),
            completed_at=_utcnow(),
            expires_at=existing.expires_at if existing is not None else None,
        )
        self._records[identity] = record
        return record

    def has_fingerprint_conflict(self, identity: tuple[str, str, str], incoming_fingerprint: str) -> bool:
        existing = self._records.get(identity)
        return existing is not None and existing.request_fingerprint != incoming_fingerprint


def workbench_request_fingerprint(
    *,
    tenant_id: str,
    actor_id: str,
    action_name: str,
    payload: dict[str, Any],
) -> str:
    canonical_payload = {
        "tenant_id": str(tenant_id),
        "actor_id": str(actor_id),
        "action_name": str(action_name),
        "payload": _fingerprint_payload(payload),
    }
    encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint_payload(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            if key.lower() in _FINGERPRINT_EXCLUDED_KEYS:
                continue
            cleaned[key] = _fingerprint_payload(raw_item)
        return cleaned
    if isinstance(value, list):
        return [_fingerprint_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_fingerprint_payload(item) for item in value]
    return value


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                continue
            sanitized[key] = _sanitize_payload(raw_item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _SENSITIVE_KEYS or any(token in normalized for token in ("secret", "token", "password", "cookie"))


def _datetime_to_storage(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
