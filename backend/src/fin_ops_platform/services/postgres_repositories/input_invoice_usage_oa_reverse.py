from __future__ import annotations

from typing import Any

from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
    RELEASED_BATCH_STATUSES,
    InputInvoiceUsageOaReverseBatch,
    InputInvoiceUsageOaReverseInvalidTransitionError,
    _assert_draft_claim_available,
    _assert_draft_claim_write,
    _batch_from_storage,
    _batch_to_storage,
    _decimal,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb as _jsonb
from fin_ops_platform.services.postgres_repositories.common import serialize_value as _serialize_jsonb_value
from fin_ops_platform.services.oa_applicant_credentials import (
    OaApplicantCredentialConflictError,
    OaApplicantCredentialError,
)
from fin_ops_platform.services.postgres_repositories.oa_applicant_credentials import PostgresOaApplicantCredentialRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


def input_invoice_usage_oa_reverse_statistics_snapshot(connection: Any) -> dict[str, object]:
    row = connection.fetch_one(
        """
        select
            count(*)::integer as batch_count,
            max(created_at)::text as max_created_at
        from app.input_invoice_usage_oa_reverse_batches
        """
    )
    batch_count = int(row.get("batch_count") or 0) if isinstance(row, dict) else 0
    max_created_at = str(row.get("max_created_at") or "") if isinstance(row, dict) else ""
    return {
        "batch_count": batch_count,
        "source_version": f"rows:{batch_count}|max_created_at:{max_created_at}",
    }


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

    def invoice_occupancy(self, invoice_ids: list[str]) -> dict[str, dict[str, str]]:
        return self._invoice_occupancy(self._connection, invoice_ids)

    @staticmethod
    def _invoice_occupancy(connection: Any, invoice_ids: list[str]) -> dict[str, dict[str, str]]:
        if not invoice_ids:
            return {}
        rows = connection.fetch_all(
            """select batch_id, status, invoice_ids
               from app.input_invoice_usage_oa_reverse_batches
               where invoice_ids && %s::text[] and status <> all(%s::text[])
               order by created_at, batch_id""",
            (invoice_ids, sorted(RELEASED_BATCH_STATUSES)),
        )
        requested = set(invoice_ids)
        return {
            invoice_id: {"occupiedBatchId": str(row["batch_id"]), "occupiedBatchStatus": str(row["status"])}
            for row in rows for invoice_id in row["invoice_ids"] if invoice_id in requested
        }

    def claim_draft_creation(self, batch: InputInvoiceUsageOaReverseBatch, *, expected_version: int) -> None:
        self.save_batch(batch, claim_expected_version=expected_version)

    @staticmethod
    def assert_applicant_deletable(connection: Any, target_applicant_code: str) -> None:
        """Called with the credential row locked, also held by draft reservation."""
        pending = connection.fetch_one(
            """select batch_id from app.input_invoice_usage_oa_reverse_batches
               where target_applicant_code = %s
                 and nullif(raw_payload->'operation_idempotency'->>'draft_request', '') is not null
                 and nullif(oa_draft_id, '') is null
               limit 1""",
            (target_applicant_code,),
        )
        if pending:
            raise OaApplicantCredentialConflictError("该申请人有正在创建或结果未明的 OA 草稿，请先核实。")

    def save_batch(self, batch: InputInvoiceUsageOaReverseBatch, *, claim_expected_version: int | None = None) -> None:
        with self._connection.transaction() as tx:
            if claim_expected_version is not None:
                try:
                    PostgresOaApplicantCredentialRepository.lock_verified_credential(tx, batch.target_applicant_code)
                except OaApplicantCredentialError as exc:
                    raise InputInvoiceUsageOaReverseInvalidTransitionError(
                        "反提 OA 申请人凭据已删除或尚未验证，请重新配置。", code="oa_reverse_applicant_unavailable",
                    ) from exc
            PostgresWorkbenchRelationRepository(tx).acquire_relation_member_locks(
                batch.invoice_ids, row_types=["invoice"] * len(batch.invoice_ids))
            # Relation commands use the same member locks and key-share these canonical rows.
            tx.fetch_all(
                """select id from app.invoices
                   where id::text = any(%s::text[]) or legacy_mongo_id = any(%s::text[])
                   order by id for update""",
                (batch.invoice_ids, batch.invoice_ids),
            )
            current = tx.fetch_one(
                "select status, raw_payload from app.input_invoice_usage_oa_reverse_batches where batch_id = %s for update",
                (batch.batch_id,),
            )
            stored = _batch_from_storage(current["raw_payload"]) if current else None
            if claim_expected_version is not None:
                _assert_draft_claim_available(stored, claim_expected_version)
            _assert_draft_claim_write(stored, batch)
            if batch.status not in RELEASED_BATCH_STATUSES:
                if claim_expected_version is not None or current is None or current["status"] in RELEASED_BATCH_STATUSES:
                    linked = tx.fetch_one(
                        """select case_id from app.workbench_pair_relations relation
                           where relation.status = 'active' and relation.row_ids && %s::text[]
                             and 'oa' = any(relation.row_types)
                             and exists (
                               select 1 from unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
                               where member.row_type = 'invoice' and member.row_id = any(%s::text[])
                             ) limit 1""",
                        (batch.invoice_ids, batch.invoice_ids),
                    )
                    if linked:
                        raise InputInvoiceUsageOaReverseInvalidTransitionError(
                            "所选发票已有 OA 关系，请重新选择。", code="invalid_oa_reverse_selection")
                rows = tx.fetch_all(
                    """select batch_id from app.input_invoice_usage_oa_reverse_batches
                       where invoice_ids && %s::text[] and status <> all(%s::text[])
                         and batch_id <> %s limit 1""",
                    (batch.invoice_ids, sorted(RELEASED_BATCH_STATUSES), batch.batch_id),
                )
                if rows:
                    raise InputInvoiceUsageOaReverseInvalidTransitionError(
                        "发票已有反提 OA 批次，请处理现有批次。", code="invoice_oa_reverse_occupied")
            self._save_batch(tx, batch)

    @staticmethod
    def _save_batch(connection: Any, batch: InputInvoiceUsageOaReverseBatch) -> None:
        payload = _batch_to_storage(batch)
        connection.execute(
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
