-- Close the remaining financial-operation idempotency and worker retry gaps.

set local lock_timeout = '5s';
set local statement_timeout = '2min';

alter table job.import_jobs
    add column if not exists request_fingerprint text;

alter table job.background_jobs
    add column if not exists idempotency_key text,
    add column if not exists request_fingerprint text;

create unique index if not exists background_jobs_idempotency_uidx
    on job.background_jobs (owner_id, job_type, idempotency_key)
    where idempotency_key is not null;

create unique index if not exists background_jobs_active_data_reset_uidx
    on job.background_jobs (job_type)
    where job_type = 'settings_data_reset' and status in ('queued', 'running');

create table if not exists job.runtime_event_attempts (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null references job.outbox_events(id) on delete cascade,
    queue_attempt integer not null,
    worker_id text not null,
    outcome text not null,
    error text,
    result_summary jsonb not null default '{}'::jsonb,
    started_at timestamptz not null,
    finished_at timestamptz,
    duration_ms bigint,
    created_at timestamptz not null default now(),
    check (queue_attempt > 0),
    check (outcome in (
        'processing', 'succeeded', 'retry_scheduled', 'failed',
        'dead_lettered', 'released', 'deferred', 'lease_expired'
    )),
    check (jsonb_typeof(result_summary) = 'object'),
    check (duration_ms is null or duration_ms >= 0)
);

create index if not exists runtime_event_attempts_event_attempt_idx
    on job.runtime_event_attempts (event_id, queue_attempt);

create index if not exists runtime_event_attempts_event_time_idx
    on job.runtime_event_attempts (event_id, started_at desc, id desc);

create index if not exists runtime_event_attempts_outcome_time_idx
    on job.runtime_event_attempts (outcome, started_at desc, id desc);

create or replace function job.capture_runtime_event_attempt()
returns trigger
language plpgsql
as $$
declare
    final_outcome text;
begin
    if new.status = 'processing'
       and (old.status is distinct from 'processing' or new.attempts > old.attempts) then
        update job.runtime_event_attempts
        set
            outcome = 'lease_expired',
            finished_at = coalesce(new.locked_at, now()),
            duration_ms = greatest(
                0,
                floor(extract(epoch from (coalesce(new.locked_at, now()) - started_at)) * 1000)::bigint
            )
        where event_id = new.id
          and finished_at is null;

        insert into job.runtime_event_attempts(
            event_id, queue_attempt, worker_id, outcome, started_at
        )
        values (
            new.id,
            new.attempts,
            coalesce(nullif(new.locked_by, ''), 'unknown-worker'),
            'processing',
            coalesce(new.locked_at, now())
        );
    end if;

    if old.status = 'processing' and new.status <> 'processing' then
        final_outcome := case
            when new.status = 'done'
                 and new.raw_payload->'runtime_defer_superseded'
                     is distinct from old.raw_payload->'runtime_defer_superseded'
                then 'deferred'
            when new.status = 'done' then 'succeeded'
            when new.status = 'dead_lettered' then 'dead_lettered'
            when new.status = 'failed' then 'failed'
            when new.status = 'pending'
                 and new.raw_payload->'runtime_defer' is distinct from old.raw_payload->'runtime_defer'
                then 'deferred'
            when new.status = 'pending'
                 and new.raw_payload->'runtime_shutdown_release'
                     is distinct from old.raw_payload->'runtime_shutdown_release'
                then 'released'
            when new.status = 'pending' then 'retry_scheduled'
            else 'failed'
        end;

        update job.runtime_event_attempts as attempts
        set
            outcome = final_outcome,
            error = new.last_error,
            result_summary = case
                when jsonb_typeof(new.raw_payload->'runtime_result') = 'object'
                    then new.raw_payload->'runtime_result'
                when jsonb_typeof(new.raw_payload->'runtime_failure') = 'object'
                    then new.raw_payload->'runtime_failure'
                when jsonb_typeof(new.raw_payload->'runtime_defer') = 'object'
                    then new.raw_payload->'runtime_defer'
                when jsonb_typeof(new.raw_payload->'runtime_shutdown_release') = 'object'
                    then new.raw_payload->'runtime_shutdown_release'
                when jsonb_typeof(new.raw_payload->'runtime_defer_superseded') = 'object'
                    then new.raw_payload->'runtime_defer_superseded'
                else '{}'::jsonb
            end,
            finished_at = case
                when new.status in ('done', 'failed', 'dead_lettered')
                    then coalesce(new.processed_at, now())
                else now()
            end,
            duration_ms = greatest(
                0,
                floor(extract(epoch from (
                    case
                        when new.status in ('done', 'failed', 'dead_lettered')
                            then coalesce(new.processed_at, now())
                        else now()
                    end - attempts.started_at
                )) * 1000)::bigint
            )
        where attempts.id = (
            select candidate.id
            from job.runtime_event_attempts as candidate
            where candidate.event_id = new.id
              and candidate.queue_attempt = old.attempts
              and candidate.finished_at is null
            order by candidate.started_at desc, candidate.id desc
            limit 1
        );
    end if;

    return new;
end;
$$;

drop trigger if exists outbox_events_capture_attempt_trg on job.outbox_events;
create trigger outbox_events_capture_attempt_trg
after update of status, attempts on job.outbox_events
for each row execute function job.capture_runtime_event_attempt();

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant usage on schema job to fin_ops_app_runtime;
        grant select, insert, update on job.runtime_event_attempts to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant usage on schema job to fin_ops_app;
        grant select on job.runtime_event_attempts to fin_ops_app;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant usage on schema job to fin_ops_api;
        grant select, insert, update on job.runtime_event_attempts to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant usage on schema job to fin_ops_worker;
        grant select, insert, update on job.runtime_event_attempts to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant usage on schema job to fin_ops_readonly;
        grant select on job.runtime_event_attempts to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant usage, create on schema job to fin_ops_migrator;
        grant select, insert, update, delete on job.runtime_event_attempts to fin_ops_migrator;
    end if;
end $$;
