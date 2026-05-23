create table if not exists job.import_jobs (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    import_type text not null,
    import_session_id text,
    source_file_id text,
    idempotency_key text,
    status text not null default 'pending',
    stage text not null default 'queued',
    priority text not null default 'normal',
    attempt_count integer not null default 0,
    max_attempts integer not null default 5,
    last_error text,
    payload jsonb not null default '{}'::jsonb,
    result_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_by text,
    trace_id text,
    available_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz,
    locked_by text,
    locked_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (status in ('pending', 'processing', 'succeeded', 'failed', 'canceled')),
    check (priority in ('low', 'normal', 'high', 'urgent')),
    check (attempt_count >= 0),
    check (max_attempts > 0)
);

create unique index if not exists import_jobs_idempotency_uidx
    on job.import_jobs (tenant_id, idempotency_key)
    where idempotency_key is not null;

create index if not exists import_jobs_claim_idx
    on job.import_jobs (status, available_at, priority, created_at, id)
    where status = 'pending';

create index if not exists import_jobs_processing_lock_idx
    on job.import_jobs (status, locked_at)
    where status = 'processing';

create index if not exists import_jobs_type_status_idx
    on job.import_jobs (tenant_id, import_type, status, created_at desc);

create index if not exists import_jobs_trace_idx
    on job.import_jobs (trace_id)
    where trace_id is not null;

create or replace view job.import_job_status_v1 as
select
    id::text as import_job_id,
    tenant_id,
    import_type,
    import_session_id,
    source_file_id,
    idempotency_key,
    status,
    stage,
    priority,
    attempt_count,
    max_attempts,
    last_error,
    created_by,
    trace_id,
    available_at,
    started_at,
    finished_at,
    locked_by,
    locked_at,
    created_at,
    updated_at
from job.import_jobs;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant usage on schema job to fin_ops_api;
        grant select, insert, update on job.import_jobs to fin_ops_api;
        grant select on job.import_job_status_v1 to fin_ops_api;
        grant usage, select on all sequences in schema job to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant usage on schema job to fin_ops_worker;
        grant select, insert, update on job.import_jobs to fin_ops_worker;
        grant select on job.import_job_status_v1 to fin_ops_worker;
        grant usage, select on all sequences in schema job to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant usage on schema job to fin_ops_readonly;
        grant select on job.import_jobs to fin_ops_readonly;
        grant select on job.import_job_status_v1 to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant usage, create on schema job to fin_ops_migrator;
        grant select, insert, update, delete on job.import_jobs to fin_ops_migrator;
        grant select on job.import_job_status_v1 to fin_ops_migrator;
        grant usage, select on all sequences in schema job to fin_ops_migrator;
    end if;
end $$;
