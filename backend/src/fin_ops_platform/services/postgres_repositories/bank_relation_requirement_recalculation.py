from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb


class PostgresBankRelationRequirementRecalculationRequestRepository:
    """Atomically commits rule settings, the visible job, and its durable event."""

    def __init__(self, connection: Any, queue_repository: Any, state_store: Any) -> None:
        self._connection = connection
        self._queue = queue_repository
        self._state_store = state_store

    def commit(
        self,
        *,
        next_snapshot: dict[str, Any],
        expected_version: int,
        job_payload: dict[str, object] | None,
        changed_tag_codes: list[str],
    ) -> dict[str, Any] | None:
        job_payload = dict(job_payload) if isinstance(job_payload, dict) else None
        job_id = str((job_payload or {}).get("job_id") or "").strip()
        owner_id = str((job_payload or {}).get("owner_user_id") or "").strip()
        target_version = int(
            (next_snapshot.get("bank_flow_rule_batch_tag_rules") or {}).get("version") or 1
        )
        if changed_tag_codes and (not job_id or not owner_id):
            raise ValueError("rule recalculation request is incomplete")
        with self._connection.transaction() as transaction:
            saved = self._state_store.save_app_settings_for_bank_flow_rule_version_in_transaction(
                next_snapshot,
                expected_version=expected_version,
                transaction=transaction,
            )
            if not isinstance(saved, dict):
                return None
            if not changed_tag_codes:
                return saved
            assert job_payload is not None
            transaction.execute(
                """
                insert into job.background_jobs (
                    job_id, job_type, status, owner_id, visibility, source,
                    affected_months, progress, result_summary, raw_payload,
                    idempotency_key, request_fingerprint
                ) values (%s, %s, 'queued', %s, 'system', %s, array[]::text[], %s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    str(job_payload.get("type") or "bank_relation_requirement_recalculation"),
                    owner_id,
                    json.dumps(job_payload.get("source") or {}, ensure_ascii=False),
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
                    str(job_payload.get("idempotency_key") or ""),
                    str(job_payload.get("request_fingerprint") or ""),
                ),
            )
            self._queue.enqueue_in_transaction(
                transaction=transaction,
                event_type="settings.bank_relation_requirements.recalculate.requested",
                aggregate_type="bank_flow_rule_batch_tag_rules",
                aggregate_id=str(target_version),
                scope_type="settings",
                scope_key="bank_flow_rule_batch_tag_rules",
                dedupe_key=f"bank-relation-requirements:version:{target_version}",
                source_version=target_version,
                priority="high",
                payload={
                    "job_id": job_id,
                    "owner_user_id": owner_id,
                    "target_rule_version": target_version,
                    "changed_tag_codes": changed_tag_codes,
                },
            )
        return saved
