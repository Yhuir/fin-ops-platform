from __future__ import annotations

from contextlib import nullcontext
from typing import Any


class PostgresImportLifecycleRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_events(
        self, *, page: int = 1, page_size: int = 50,
        batch_type: str = "", status: str = "", search: str = "",
        start_at: Any = None, end_at: Any = None, batch_id: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = []
        params: list[Any] = []
        for column, value in (("batch_type", batch_type), ("display_status", status), ("batch_id", batch_id)):
            if value:
                conditions.append(f"{column} = %s")
                params.append(value)
        if search:
            conditions.append("strpos(lower(coalesce(source_name, '')), lower(%s)) > 0")
            params.append(search)
        if start_at is not None:
            conditions.append("imported_at >= %s")
            params.append(start_at)
        if end_at is not None:
            conditions.append("imported_at < %s")
            params.append(end_at)
        where_sql = "where " + " and ".join(conditions) if conditions else ""
        params.extend((page_size, (page - 1) * page_size))
        # Count and rows share one statement snapshot; ownership hydration is limited to the page.
        result = self._connection.fetch_all(
            f"""
            with events as (
              select
                batch.id as batch_uuid, batch.legacy_mongo_id as legacy_batch_id,
                coalesce(batch.legacy_mongo_id, batch.id::text) as event_id,
                coalesce(batch.legacy_mongo_id, batch.id::text) as batch_id,
                batch.batch_type,
                case when batch.batch_type = 'bank_transaction' then 'bank_transactions' else 'manual' end as source_key,
                case when batch.batch_type = 'bank_transaction' then '流水导入' else '手工导入' end as label,
                batch.source_name, coalesce(file.imported_by, batch.imported_by) as imported_by,
                batch.success_count::bigint as count, batch.updated_count, batch.raw_payload,
                coalesce(file.uploaded_at, batch.imported_at) as imported_at,
                file.file_id, file.session_id,
                file.selected_bank_name, file.selected_bank_last4, file.detected_bank_name, file.detected_last4,
                latest_job.import_job_id, latest_job.stage as job_stage, latest_job.last_error as job_error,
                case
                  when 'withdrawn' in (batch.status, file.file_status, file.session_status) then 'withdrawn'
                  when 'reverted' in (batch.status, file.file_status, file.session_status)
                    or latest_job.status = 'canceled' then 'discarded'
                  when latest_job.status = 'failed' or batch.status = 'failed' then 'failed'
                  when latest_job.status = 'processing' then 'processing'
                  when latest_job.status = 'pending' then 'queued'
                  when batch.status = 'completed_with_errors'
                    or (latest_job.status = 'succeeded' and latest_job.result_payload->>'outcome' = 'partial_success')
                    then 'partial_success'
                  when batch.status = 'completed' and coalesce(file.file_status, '') in ('', 'confirmed') then 'succeeded'
                  when latest_job.status = 'succeeded' then 'inconsistent'
                  when file.file_status in ('duplicate_file', 'preview_ready_with_errors', 'source_control_mismatch', 'unrecognized_template')
                    or file.session_status = 'preview_ready_with_errors' then 'preview_failed'
                  when file.session_status = 'preview_ready'
                    or (batch.status = 'pending' and coalesce(file.file_status, '') in ('', 'preview_ready')) then 'awaiting_confirmation'
                  else 'unknown'
                end as display_status
              from app.import_batches batch
              left join lateral (
                select coalesce(import_file.legacy_mongo_id, import_file.id::text) as file_id,
                  import_file.session_id, import_file.status as file_status, import_file.uploaded_at,
                  coalesce(import_file.raw_payload->'normalized_payload'->>'imported_by', import_file.uploaded_by) as imported_by,
                  import_file.raw_payload->'normalized_payload'->>'session_status' as session_status,
                  import_file.raw_payload->'normalized_payload'->>'selected_bank_name' as selected_bank_name,
                  import_file.raw_payload->'normalized_payload'->>'selected_bank_last4' as selected_bank_last4,
                  import_file.raw_payload->'normalized_payload'->>'detected_bank_name' as detected_bank_name,
                  import_file.raw_payload->'normalized_payload'->>'detected_last4' as detected_last4
                from app.import_files import_file
                where coalesce(import_file.raw_payload->'normalized_payload'->>'batch_id',
                  import_file.raw_payload->'normalized_payload'->>'preview_batch_id') in (batch.legacy_mongo_id, batch.id::text)
                order by import_file.uploaded_at desc, import_file.id desc limit 1
              ) file on true
              left join lateral (
                select import_job.id::text as import_job_id, status, stage, last_error, result_payload
                from job.import_jobs import_job where import_job.import_session_id = file.session_id
                order by import_job.created_at desc, import_job.id desc limit 1
              ) latest_job on true
              where batch.batch_type in ('bank_transaction', 'input_invoice', 'output_invoice')
            ), filtered as (select * from events {where_sql})
            select totals.total, page.*, coalesce(owned.created_count, 0)::bigint as created_count
            from (select count(*)::bigint as total from filtered) totals
            left join lateral (
              select * from filtered order by imported_at desc nulls last, event_id desc limit %s offset %s
            ) page on true
            left join lateral (
              select count(distinct bank.id)::bigint as created_count
              from app.import_batch_rows batch_row
              join app.bank_transactions bank on batch_row.linked_object_type = 'bank_transaction'
                and batch_row.linked_object_id in (bank.legacy_mongo_id, bank.id::text)
              where page.batch_type = 'bank_transaction' and batch_row.decision = 'created'
                and (batch_row.import_batch_id = page.batch_uuid or batch_row.legacy_batch_id = page.legacy_batch_id)
                and (bank.source_batch_id = page.batch_uuid or bank.legacy_source_batch_id = page.legacy_batch_id)
            ) owned on true
            order by page.imported_at desc nulls last, page.event_id desc
            """, tuple(params),
        )
        return [dict(row) for row in result if row["event_id"] is not None], int(result[0]["total"])

    def discard_preview_session(self, *, session_id: str, imported_by: str, transaction: Any = None) -> int:
        with (nullcontext(transaction) if transaction is not None else self._connection.transaction()) as transaction:
            rows = transaction.fetch_all(
                """
                select
                  import_file.id::text,
                  import_file.status,
                  coalesce(
                    import_file.raw_payload->'normalized_payload'->>'imported_by',
                    import_file.uploaded_by
                  ) as imported_by,
                  coalesce(
                    import_file.raw_payload->'normalized_payload'->>'batch_id',
                    import_file.raw_payload->'normalized_payload'->>'preview_batch_id'
                  ) as batch_id
                from app.import_files import_file
                where import_file.session_id = %s
                  and import_file.status <> 'deleted'
                order by import_file.id
                for update
                """,
                (session_id,),
            ) or []
            if not rows:
                raise KeyError(session_id)
            if any(str(row.get("imported_by") or "") != str(imported_by) for row in rows):
                raise PermissionError("import session belongs to another user")
            statuses = {str(row.get("status") or "") for row in rows}
            if "confirmed" in statuses:
                raise ValueError("confirmed import sessions cannot be discarded")
            active_job = transaction.fetch_one(
                """
                select import_job.id::text as import_job_id, status
                from job.import_jobs import_job
                where import_session_id = %s
                  and status in ('pending', 'processing', 'succeeded')
                order by created_at desc, import_job.id desc
                limit 1
                """,
                (session_id,),
            )
            if active_job:
                raise ValueError(f"import session has an active or completed job: {active_job['status']}")
            batch_ids = sorted({str(row.get("batch_id") or "") for row in rows if str(row.get("batch_id") or "")})
            if batch_ids:
                transaction.execute(
                    """
                    update app.import_batches
                    set status = 'reverted',
                        raw_payload = jsonb_set(
                          raw_payload,
                          '{normalized_payload,status}',
                          to_jsonb('reverted'::text),
                          true
                        ),
                        updated_at = now()
                    where status = 'pending'
                      and (legacy_mongo_id = any(%s) or id::text = any(%s))
                    """,
                    (batch_ids, batch_ids),
                )
            transaction.execute(
                """
                update app.import_files
                set
                  status = 'reverted',
                  raw_payload = jsonb_set(
                    jsonb_set(raw_payload, '{normalized_payload,status}', '"reverted"'::jsonb, true),
                    '{normalized_payload,session_status}', '"reverted"'::jsonb, true
                  )
                where session_id = %s
                  and status <> 'reverted'
                """,
                (session_id,),
            )
            return len(rows)

    @staticmethod
    def withdrawal_payload(row: dict[str, Any]) -> dict[str, Any] | None:
        raw_payload = row.get("raw_payload")
        if not isinstance(raw_payload, dict):
            return None
        normalized = raw_payload.get("normalized_payload")
        if not isinstance(normalized, dict):
            return None
        withdrawal = normalized.get("withdrawal")
        return dict(withdrawal) if isinstance(withdrawal, dict) else None
