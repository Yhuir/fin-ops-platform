alter table job.import_jobs
    add column version bigint not null default 1,
    add column claim_version bigint not null default 0,
    add column acknowledged_at timestamptz;
alter table job.import_jobs drop constraint import_jobs_status_check;
alter table job.import_jobs add constraint import_jobs_status_check
    check (status in ('pending','processing','awaiting_confirmation','needs_review','succeeded','failed','canceled'));
-- Existing confirmed intents continue from their persisted payload, never from an outbox receipt.
update job.import_jobs set stage='commit' where stage not in ('prepare','commit') and status in ('pending','processing','failed');
-- Deployment stops the legacy import consumer before this migration. Invalidate its lease.
update job.import_jobs set status='pending', locked_by=null, locked_at=null,
    claim_version=claim_version+1, version=version+1, available_at=now(), updated_at=now()
    where status='processing';
update job.import_jobs set acknowledged_at=coalesce(finished_at,updated_at,now())
    where status in ('succeeded','canceled');
create index import_jobs_owner_active_idx on job.import_jobs(created_by, created_at desc)
    where acknowledged_at is null;
create index import_jobs_session_idx on job.import_jobs(import_session_id, created_at desc)
    where import_session_id is not null;
-- Keep old outbox history as history; only retire events with an existing authoritative job.
update job.outbox_events e set status='done', processed_at=coalesce(processed_at,now()), locked_by=null, locked_at=null, updated_at=now()
from job.import_jobs j where e.event_type='import.process.requested'
    and e.payload->>'import_job_id'=j.id::text and e.status in ('pending','processing','failed');

-- An event without a job cannot execute. Preserve it as explicit migration evidence.
update job.outbox_events e set status='failed', locked_by=null, locked_at=null,
    last_error='import_queue_migration_orphan: missing canonical import job; requires explicit repair',
    updated_at=now()
where e.event_type='import.process.requested' and e.status in ('pending','processing')
    and not exists (select 1 from job.import_jobs j where e.payload->>'import_job_id'=j.id::text);
