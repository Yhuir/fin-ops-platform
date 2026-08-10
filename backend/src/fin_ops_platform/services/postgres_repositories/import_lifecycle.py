from __future__ import annotations

from typing import Any


class PostgresImportLifecycleRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_events(self, *, page: int = 1, page_size: int = 50) -> tuple[list[dict[str, Any]], int]:
        limit = min(max(int(page_size), 1), 100)
        offset = (max(int(page), 1) - 1) * limit
        where_sql = "where batch.batch_type in ('bank_transaction', 'input_invoice', 'output_invoice')"
        total_row = self._connection.fetch_one(
            f"select count(*)::bigint as total from app.import_batches batch {where_sql}"
        ) or {}
        rows = self._connection.fetch_all(
            f"""
            select
              coalesce(batch.legacy_mongo_id, batch.id::text) as event_id,
              case when batch.batch_type = 'bank_transaction' then 'bank_transactions' else 'manual' end as source_key,
              case when batch.batch_type = 'bank_transaction' then '流水导入' else '手工导入' end as label,
              batch.source_name,
              coalesce(file.imported_by, batch.imported_by) as imported_by,
              batch.success_count::bigint as count,
              null::bigint as supplementary_count,
              coalesce(file.uploaded_at, batch.imported_at) as imported_at,
              batch.status as batch_status,
              file.file_id,
              file.session_id,
              file.file_status,
              file.session_status,
              latest_job.import_job_id,
              latest_job.status as job_status,
              latest_job.stage as job_stage,
              latest_job.last_error as job_error
            from app.import_batches batch
            left join lateral (
              select
                coalesce(import_file.legacy_mongo_id, import_file.id::text) as file_id,
                import_file.session_id,
                import_file.status as file_status,
                import_file.uploaded_at,
                coalesce(
                  import_file.raw_payload->'normalized_payload'->>'imported_by',
                  import_file.uploaded_by
                ) as imported_by,
                import_file.raw_payload->'normalized_payload'->>'session_status' as session_status
              from app.import_files import_file
              where coalesce(
                import_file.raw_payload->'normalized_payload'->>'batch_id',
                import_file.raw_payload->'normalized_payload'->>'preview_batch_id'
              ) in (batch.legacy_mongo_id, batch.id::text)
              order by import_file.uploaded_at desc, import_file.id desc
              limit 1
            ) file on true
            left join lateral (
              select import_job.id::text as import_job_id, status, stage, last_error
              from job.import_jobs import_job
              where import_job.import_session_id = file.session_id
              order by import_job.created_at desc, import_job.id desc
              limit 1
            ) latest_job on true
            {where_sql}
            order by coalesce(file.uploaded_at, batch.imported_at) desc, event_id desc
            limit %s offset %s
            """,
            (limit, offset),
        ) or []
        return [dict(row) for row in rows], int(total_row.get("total") or 0)

    def list_active_sessions(
        self,
        *,
        imported_by: str,
        mode: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized_limit = min(max(int(limit), 1), 50)
        params: list[Any] = [str(imported_by)]
        mode_clause = ""
        if mode == "bank_transaction":
            mode_clause = "and payload.data->>'batch_type' = 'bank_transaction'"
        elif mode == "invoice":
            mode_clause = "and payload.data->>'batch_type' in ('input_invoice', 'output_invoice')"
        rows = self._connection.fetch_all(
            f"""
            with active_sessions as (
              select
                import_file.session_id,
                max(import_file.uploaded_at) as updated_at,
                max(payload.data->>'created_at') as created_at,
                max(payload.data->>'session_status') as session_status,
                max(payload.data->>'batch_type') as batch_type,
                max(coalesce(payload.data->>'imported_by', import_file.uploaded_by)) as imported_by,
                bool_or(import_file.status = 'preview_ready') as has_confirmable_file,
                count(*)::bigint as file_count
              from app.import_files import_file
              cross join lateral (
                select coalesce(
                  import_file.raw_payload->'normalized_payload',
                  import_file.raw_payload,
                  '{{}}'::jsonb
                ) as data
              ) payload
              where import_file.status not in ('confirmed', 'skipped', 'reverted', 'deleted')
                and coalesce(payload.data->>'imported_by', import_file.uploaded_by) = %s
                {mode_clause}
              group by import_file.session_id
            )
            select
              active_sessions.*,
              latest_job.import_job_id,
              latest_job.status as job_status,
              latest_job.stage as job_stage,
              latest_job.last_error as job_error
            from active_sessions
            left join lateral (
              select import_job.id::text as import_job_id, status, stage, last_error
              from job.import_jobs import_job
              where import_job.import_session_id = active_sessions.session_id
              order by import_job.created_at desc, import_job.id desc
              limit 1
            ) latest_job on true
            order by active_sessions.updated_at desc, active_sessions.session_id desc
            limit %s
            """,
            (*params, normalized_limit),
        ) or []
        return [dict(row) for row in rows]

    def discard_preview_session(self, *, session_id: str, imported_by: str) -> int:
        with self._connection.transaction() as transaction:
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
                    set status = 'reverted', updated_at = now()
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
