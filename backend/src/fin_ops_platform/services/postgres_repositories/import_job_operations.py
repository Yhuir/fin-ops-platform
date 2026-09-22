"""Bounded administrator reads and atomic disposition of durable import jobs."""
from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.import_job_status import scoped_import_jobs

_JOB_COLUMNS = """id::text as job_id, import_type, import_session_id as session_id,
    created_by, status, stage, version, attempt_count, max_attempts,
    created_at::text, updated_at::text, finished_at::text, acknowledged_at::text,
    result_payload->'disposition' as disposition, affected_domains,
    case when position('selected files require review before confirmation: ' in last_error)=1
      then 'review_required' else result_payload->>'error_code' end as error_code"""
_ACTIVE = "acknowledged_at is null and status in ('pending','processing','failed','awaiting_confirmation','needs_review')"


class ImportJobOperationsRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def list_jobs(self, *, page: int, page_size: int) -> dict[str, Any]:
        # Count and page share one statement snapshot, including an empty last page.
        rows = self.connection.fetch_all(scoped_import_jobs(f"""
            select * from job.import_jobs where {_ACTIVE}
            order by updated_at desc,id desc limit %s offset %s
        """) + f"""
            select totals.total, page.* from
              (select count(*)::int as total from job.import_jobs where {_ACTIVE}) totals
            left join lateral (
              select {_JOB_COLUMNS},
                (select min(f.original_filename) from app.import_files f where f.session_id=scoped_jobs.import_session_id
                 and (coalesce(payload->'selected_file_ids','[]'::jsonb)='[]'::jsonb
                      or payload->'selected_file_ids' ? coalesce(f.legacy_mongo_id,f.id::text))) as file_name,
                (select count(*)::int from app.import_files f where f.session_id=scoped_jobs.import_session_id
                 and (coalesce(payload->'selected_file_ids','[]'::jsonb)='[]'::jsonb
                      or payload->'selected_file_ids' ? coalesce(f.legacy_mongo_id,f.id::text))) as file_count
              from scoped_jobs order by updated_at desc,id desc
            ) page on true
        """, (page_size, (page - 1) * page_size))
        total = rows[0]['total']
        return {'rows': [{k: v for k, v in row.items() if k != 'total'} for row in rows if row['job_id']],
                'pagination': {'page': page, 'page_size': page_size, 'total': total,
                               'has_more': page * page_size < total}}

    def detail(self, job_id: str, *, file_page: int, page_size: int = 20) -> dict[str, Any]:
        with self.connection.transaction() as tx:
            tx.execute('set transaction isolation level repeatable read read only')
            job = tx.fetch_one(scoped_import_jobs('select * from job.import_jobs where id=%s')
                              + f'select {_JOB_COLUMNS}, last_error from scoped_jobs', (job_id,))
            if job is None:
                raise KeyError(job_id)
            files = tx.fetch_all("""
                with selected_files as materialized (
                  select f.id, coalesce(f.legacy_mongo_id,f.id::text) as file_id,
                    f.original_filename as file_name, f.status,
                    f.raw_payload->'normalized_payload' as preview
                  from job.import_jobs j join app.import_files f on f.session_id=j.import_session_id
                  where j.id=%s and (coalesce(j.payload->'selected_file_ids','[]'::jsonb)='[]'::jsonb
                    or j.payload->'selected_file_ids' ? coalesce(f.legacy_mongo_id,f.id::text))
                )
                select totals.total, page.* from (select count(*)::int as total from selected_files) totals
                left join lateral (
                  select file_id,file_name,status,preview->>'message' as message,
                    preview->>'error_count' as error_count,
                    preview->>'suspected_duplicate_count' as suspected_duplicate_count,
                    preview->>'preview_batch_id' as preview_batch_id,
                    preview->>'batch_id' as batch_id,
                    evidence.row_count, evidence.linked_count, evidence.identity_match_count
                  from selected_files f
                  left join lateral (
                    select count(*)::int as row_count,
                      count(*) filter (where r.decision in ('created','status_updated','duplicate_skipped')
                        and r.linked_object_id is not null)::int as linked_count,
                      count(*) filter (where i.id is not null)::int as identity_match_count
                    from app.import_batch_rows r
                    join app.import_batches b on r.import_batch_id=b.id
                    left join app.invoices i on r.source_record_type='invoice'
                      and i.source_unique_key=r.source_unique_key and i.status<>'deleted'
                    where coalesce(b.legacy_mongo_id,b.id::text)=coalesce(
                      nullif(f.preview->>'batch_id',''), f.preview->>'preview_batch_id')
                  ) evidence on true
                  order by f.id limit %s offset %s
                ) page on true
            """, (job_id, page_size, (file_page - 1) * page_size))
        total = files[0]['total']
        return {'job': job, 'files': [{k: v for k, v in row.items() if k != 'total'} for row in files if row['file_id']],
                'file_pagination': {'page': file_page, 'page_size': page_size, 'total': total,
                                    'has_more': file_page * page_size < total}}

    def dispose(self, job_id: str, *, expected_version: int, action: str, reason: str, note: str,
                actor: dict[str, str], request_id: str, on_dispose: Callable[..., None]) -> dict[str, Any]:
        with self.connection.transaction() as tx:
            row = tx.fetch_one('select *, id::text as job_id from job.import_jobs where id=%s for update', (job_id,))
            if row is None:
                raise KeyError(job_id)
            previous = row['result_payload'].get('disposition')
            if previous is not None:
                if (previous['action'], previous['reason'], previous['note'], previous['expected_version']) != (action, reason, note, expected_version):
                    raise ImportJobIdempotencyConflict('任务已由其他处理请求结束，请刷新查看结果。')
                return {'job_id': job_id, 'status': row['status'], 'version': row['version'],
                        'disposition': previous, 'idempotent_replay': True}
            if row['version'] != expected_version:
                raise ImportJobIdempotencyConflict('任务状态已变化，请刷新后再处理。')
            if not (action == 'close' and row['status'] == 'failed' or action == 'discard' and row['status'] == 'needs_review'):
                raise ImportJobIdempotencyConflict('当前任务不能执行此操作；执行中或待确认的任务请在原导入页面处理。')
            disposition = {'action': action, 'reason': reason, 'note': note, 'actor_account': actor['actor_account'],
                           'actor_name': actor['actor_name'], 'request_id': request_id, 'expected_version': expected_version}
            # The service callback owns lifecycle and audit; all share this transaction.
            on_dispose(tx, row, disposition)
            updated = tx.fetch_one("""
                update job.import_jobs set acknowledged_at=now(), updated_at=now(), version=version+1,
                  claim_version=claim_version+1,
                  status=case when %s='discard' then 'canceled' else status end,
                  result_payload=result_payload || jsonb_build_object('disposition', %s::jsonb ||
                    jsonb_build_object('handled_at',now())),
                  finished_at=coalesce(finished_at,now())
                where id=%s returning id::text as job_id,status,version,result_payload->'disposition' as disposition
            """, (action, jsonb(disposition), job_id))
            return {**updated, 'idempotent_replay': False}
