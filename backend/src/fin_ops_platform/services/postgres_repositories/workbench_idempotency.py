from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.workbench_idempotency import WorkbenchIdempotencyRecord


_COLUMNS = """
    tenant_id,
    actor_id,
    action_name,
    idempotency_key,
    request_fingerprint,
    status,
    request_payload,
    response_payload,
    source_versions,
    outbox_event_ids,
    created_at,
    completed_at,
    expires_at
"""


class PostgresWorkbenchIdempotencyRepository:
    """Durable Workbench idempotency records backed by app.workbench_idempotency_records."""

    def __init__(self, executor: Any) -> None:
        self._executor = executor

    def for_transaction(self, transaction: Any) -> "PostgresWorkbenchIdempotencyRepository":
        return PostgresWorkbenchIdempotencyRepository(transaction)

    def get_committed_or_reserved(
        self,
        tenant_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> WorkbenchIdempotencyRecord | None:
        row = self._executor.fetch_one(
            f"""
            select {_COLUMNS}
            from app.workbench_idempotency_records
            where tenant_id = %s
              and actor_id = %s
              and idempotency_key = %s
            limit 1
            """,
            (tenant_id, actor_id, idempotency_key),
        )
        return _record_from_row(row)

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
        created_at = _utcnow()
        storage = WorkbenchIdempotencyRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="reserved",
            request_payload=request_payload or {},
            created_at=created_at,
            expires_at=expires_at,
        ).to_storage_payload()
        row = self._executor.fetch_one(
            f"""
            insert into app.workbench_idempotency_records (
                {_COLUMNS}
            )
            values (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            on conflict (tenant_id, actor_id, idempotency_key) do update
            set updated_at = app.workbench_idempotency_records.updated_at
            returning {_COLUMNS}
            """,
            (
                storage["tenant_id"],
                storage["actor_id"],
                storage["action_name"],
                storage["idempotency_key"],
                storage["request_fingerprint"],
                storage["status"],
                jsonb(storage["request_payload"]),
                jsonb(storage["response_payload"]),
                jsonb(storage["source_versions"]),
                jsonb(storage["outbox_event_ids"]),
                storage["created_at"],
                storage["completed_at"],
                storage["expires_at"],
            ),
        )
        record = _record_from_row(row)
        if record is None:
            raise RuntimeError("failed to reserve Workbench idempotency record")
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
        completed_at = _utcnow()
        storage = WorkbenchIdempotencyRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="committed",
            response_payload=response_payload,
            source_versions=source_versions or {},
            outbox_event_ids=outbox_event_ids or [],
            completed_at=completed_at,
        ).to_storage_payload()
        self._executor.execute(
            """
            update app.workbench_idempotency_records
            set status = 'committed',
                response_payload = %s,
                source_versions = %s,
                outbox_event_ids = %s,
                completed_at = %s,
                updated_at = now()
            where tenant_id = %s
              and actor_id = %s
              and idempotency_key = %s
            """,
            (
                jsonb(storage["response_payload"]),
                jsonb(storage["source_versions"]),
                jsonb(storage["outbox_event_ids"]),
                storage["completed_at"],
                tenant_id,
                actor_id,
                idempotency_key,
            ),
        )
        row = self._executor.fetch_one(
            f"""
            select {_COLUMNS}
            from app.workbench_idempotency_records
            where tenant_id = %s
              and actor_id = %s
              and idempotency_key = %s
            limit 1
            """,
            (tenant_id, actor_id, idempotency_key),
        )
        record = _record_from_row(row)
        if record is None:
            return WorkbenchIdempotencyRecord(**storage)
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
        completed_at = _utcnow()
        storage = WorkbenchIdempotencyRecord(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="failed",
            response_payload=response_payload or {},
            completed_at=completed_at,
        ).to_storage_payload()
        self._executor.execute(
            """
            update app.workbench_idempotency_records
            set status = 'failed',
                response_payload = %s,
                completed_at = %s,
                updated_at = now()
            where tenant_id = %s
              and actor_id = %s
              and idempotency_key = %s
            """,
            (
                jsonb(storage["response_payload"]),
                storage["completed_at"],
                tenant_id,
                actor_id,
                idempotency_key,
            ),
        )
        row = self._executor.fetch_one(
            f"""
            select {_COLUMNS}
            from app.workbench_idempotency_records
            where tenant_id = %s
              and actor_id = %s
              and idempotency_key = %s
            limit 1
            """,
            (tenant_id, actor_id, idempotency_key),
        )
        record = _record_from_row(row)
        if record is None:
            return WorkbenchIdempotencyRecord(**storage)
        return record

    def has_fingerprint_conflict(self, identity: tuple[str, str, str], incoming_fingerprint: str) -> bool:
        tenant_id, actor_id, idempotency_key = identity
        existing = self.get_committed_or_reserved(tenant_id, actor_id, idempotency_key)
        return existing is not None and existing.request_fingerprint != incoming_fingerprint


def _record_from_row(row: dict[str, Any] | None) -> WorkbenchIdempotencyRecord | None:
    if not row:
        return None
    return WorkbenchIdempotencyRecord(
        tenant_id=str(row.get("tenant_id") or ""),
        actor_id=str(row.get("actor_id") or ""),
        action_name=str(row.get("action_name") or ""),
        idempotency_key=str(row.get("idempotency_key") or ""),
        request_fingerprint=str(row.get("request_fingerprint") or ""),
        status=str(row.get("status") or ""),
        request_payload=_dict_value(row.get("request_payload")),
        response_payload=_dict_value(row.get("response_payload")),
        source_versions=_dict_value(row.get("source_versions")),
        outbox_event_ids=_list_value(row.get("outbox_event_ids")),
        created_at=_datetime_value(row.get("created_at")),
        completed_at=_datetime_value(row.get("completed_at")),
        expires_at=_datetime_value(row.get("expires_at")),
    )


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _datetime_value(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
