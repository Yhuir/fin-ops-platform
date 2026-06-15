from __future__ import annotations

from typing import Any

from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
    InputInvoiceUsageOaReverseBatch,
    _batch_from_storage,
    _batch_to_storage,
    _decimal,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb as _jsonb
from fin_ops_platform.services.postgres_repositories.common import serialize_value as _serialize_jsonb_value


class PostgresInputInvoiceUsageOaReverseBatchRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get_batch(self, batch_id: str) -> InputInvoiceUsageOaReverseBatch | None:
        row = self._connection.fetch_one(
            """
            select raw_payload
            from app.input_invoice_usage_oa_reverse_batches
            where batch_id = %s
            """,
            (str(batch_id or "").strip(),),
        )
        return _batch_from_storage(row.get("raw_payload")) if row else None

    def find_batch_by_create_idempotency_key(self, idempotency_key: str) -> InputInvoiceUsageOaReverseBatch | None:
        normalized = str(idempotency_key or "").strip()
        if not normalized:
            return None
        row = self._connection.fetch_one(
            """
            select raw_payload
            from app.input_invoice_usage_oa_reverse_batches
            where create_idempotency_key = %s
            order by created_at desc
            limit 1
            """,
            (normalized,),
        )
        return _batch_from_storage(row.get("raw_payload")) if row else None

    def list_batches_by_status(self, statuses: list[str], *, limit: int = 50) -> list[InputInvoiceUsageOaReverseBatch]:
        normalized = [str(status or "").strip() for status in list(statuses or []) if str(status or "").strip()]
        if not normalized:
            return []
        rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.input_invoice_usage_oa_reverse_batches
            where status = any(%s)
            order by updated_at desc
            limit %s
            """,
            (normalized, max(int(limit or 50), 1)),
        )
        batches: list[InputInvoiceUsageOaReverseBatch] = []
        for row in rows:
            batch = _batch_from_storage(row.get("raw_payload"))
            if batch is not None:
                batches.append(batch)
        return batches

    def save_batch(self, batch: InputInvoiceUsageOaReverseBatch) -> None:
        payload = _batch_to_storage(batch)
        self._connection.execute(
            """
            insert into app.input_invoice_usage_oa_reverse_batches(
                batch_id, status, version, target_applicant_code, target_applicant_name,
                invoice_ids, invoice_count, total_amount, preview_hash, create_idempotency_key,
                oa_form_id, oa_draft_id, oa_draft_url, oa_row_id, oa_process_status,
                oa_detection_status, oa_detection_payload, audit_events, raw_payload,
                created_by, updated_by, created_at, updated_at
            )
            values (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            on conflict (batch_id) do update set
                status = excluded.status,
                version = excluded.version,
                target_applicant_code = excluded.target_applicant_code,
                target_applicant_name = excluded.target_applicant_name,
                invoice_ids = excluded.invoice_ids,
                invoice_count = excluded.invoice_count,
                total_amount = excluded.total_amount,
                preview_hash = excluded.preview_hash,
                create_idempotency_key = excluded.create_idempotency_key,
                oa_form_id = excluded.oa_form_id,
                oa_draft_id = excluded.oa_draft_id,
                oa_draft_url = excluded.oa_draft_url,
                oa_row_id = excluded.oa_row_id,
                oa_process_status = excluded.oa_process_status,
                oa_detection_status = excluded.oa_detection_status,
                oa_detection_payload = excluded.oa_detection_payload,
                audit_events = excluded.audit_events,
                raw_payload = excluded.raw_payload,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                batch.batch_id,
                batch.status,
                batch.version,
                batch.target_applicant_code,
                batch.target_applicant_name,
                list(batch.invoice_ids),
                len(batch.invoice_ids),
                _decimal(batch.preview_summary.get("totalWithTax")),
                batch.preview_hash,
                batch.idempotency_key,
                batch.oa_form_id,
                batch.oa_draft_id,
                batch.oa_draft_url,
                batch.oa_row_id,
                batch.oa_process_status,
                batch.oa_detection_status,
                _jsonb(_serialize_jsonb_value(dict(batch.oa_detection_payload or {}))),
                _jsonb(_serialize_jsonb_value(list(batch.audit_events or []))),
                _jsonb(_serialize_jsonb_value(payload)),
                batch.created_by,
                batch.updated_by,
                batch.created_at,
                batch.updated_at,
            ),
        )
