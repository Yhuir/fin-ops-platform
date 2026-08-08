from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb


class SettingsDataResetIdempotencyConflict(ValueError):
    pass


class SettingsDataResetAlreadyActive(RuntimeError):
    def __init__(self, payload: dict[str, object]) -> None:
        super().__init__("A settings data reset is already active.")
        self.payload = payload


class PostgresSettingsDataResetRequestRepository:
    """Atomically persists a reset job and its durable runtime event."""

    def __init__(self, connection: Any, queue_repository: Any) -> None:
        self._connection = connection
        self._queue = queue_repository

    def create_or_get(
        self,
        *,
        job_payload: dict[str, object],
        request_fingerprint: str,
        event_type: str,
        action: str,
    ) -> tuple[dict[str, object], bool]:
        owner_id = str(job_payload.get("owner_user_id") or "").strip()
        idempotency_key = str(job_payload.get("idempotency_key") or "").strip()
        job_id = str(job_payload.get("job_id") or "").strip()
        if not owner_id or not idempotency_key or not job_id:
            raise ValueError("owner_user_id, idempotency_key and job_id are required.")

        with self._connection.transaction() as transaction:
            transaction.execute(
                "select pg_advisory_xact_lock(hashtextextended('settings-data-reset', 0))"
            )
            existing = transaction.fetch_one(
                """
                select request_fingerprint, raw_payload
                from job.background_jobs
                where owner_id = %s
                  and job_type = 'settings_data_reset'
                  and idempotency_key = %s
                """,
                (owner_id, idempotency_key),
            )
            if existing is not None:
                if str(existing.get("request_fingerprint") or "") != request_fingerprint:
                    raise SettingsDataResetIdempotencyConflict(
                        "The idempotency key was already used for a different reset request."
                    )
                return self._payload(existing), False

            active = transaction.fetch_one(
                """
                select raw_payload
                from job.background_jobs
                where job_type = 'settings_data_reset'
                  and status in ('queued', 'running')
                order by created_at
                limit 1
                """
            )
            if active is not None:
                raise SettingsDataResetAlreadyActive(self._payload(active))

            transaction.execute(
                """
                insert into job.background_jobs (
                    job_id,
                    job_type,
                    status,
                    owner_id,
                    visibility,
                    source,
                    affected_months,
                    progress,
                    result_summary,
                    raw_payload,
                    idempotency_key,
                    request_fingerprint
                )
                values (%s, 'settings_data_reset', 'queued', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    owner_id,
                    str(job_payload.get("visibility") or "system"),
                    json.dumps(job_payload.get("source") or {}, ensure_ascii=False, separators=(",", ":")),
                    list(job_payload.get("affected_months") or []),
                    Jsonb(
                        {
                            "phase": job_payload.get("phase"),
                            "current": job_payload.get("current"),
                            "total": job_payload.get("total"),
                            "percent": job_payload.get("percent"),
                            "message": job_payload.get("message"),
                        }
                    ),
                    Jsonb(job_payload.get("result_summary") or {}),
                    Jsonb({"normalized_payload": job_payload}),
                    idempotency_key,
                    request_fingerprint,
                ),
            )
            self._queue.enqueue_in_transaction(
                transaction=transaction,
                event_type=event_type,
                aggregate_type="settings_data_reset",
                aggregate_id=job_id,
                scope_type="settings",
                scope_key=action,
                dedupe_key=f"settings-data-reset:{job_id}",
                priority="urgent",
                payload={"job_id": job_id, "owner_user_id": owner_id, "action": action},
            )
        return job_payload, True

    @staticmethod
    def _payload(row: dict[str, object]) -> dict[str, object]:
        raw_payload = row.get("raw_payload")
        if not isinstance(raw_payload, dict):
            return {}
        normalized = raw_payload.get("normalized_payload")
        return dict(normalized) if isinstance(normalized, dict) else dict(raw_payload)
