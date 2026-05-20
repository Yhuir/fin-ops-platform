alter table job.outbox_events
    add column if not exists tenant_id text not null default 'default',
    add column if not exists scope_type text,
    add column if not exists scope_key text,
    add column if not exists dedupe_key text,
    add column if not exists attempts integer not null default 0,
    add column if not exists processed_at timestamptz;

with normalized_attempts as (
    select id, greatest(coalesce(attempt_count, 0), coalesce(attempts, 0)) as merged_attempts
    from job.outbox_events
)
update job.outbox_events
set attempt_count = normalized_attempts.merged_attempts,
    attempts = normalized_attempts.merged_attempts
from normalized_attempts
where job.outbox_events.id = normalized_attempts.id
  and (
      job.outbox_events.attempt_count is distinct from normalized_attempts.merged_attempts
      or job.outbox_events.attempts is distinct from normalized_attempts.merged_attempts
  );

create or replace function job.sync_outbox_event_attempts()
returns trigger
language plpgsql
as $$
declare
    merged_attempts integer;
begin
    merged_attempts := greatest(coalesce(new.attempt_count, 0), coalesce(new.attempts, 0));
    new.attempt_count := merged_attempts;
    new.attempts := merged_attempts;
    return new;
end;
$$;

drop trigger if exists outbox_events_sync_attempts_trg on job.outbox_events;

create trigger outbox_events_sync_attempts_trg
    before insert or update of attempt_count, attempts on job.outbox_events
    for each row
    execute function job.sync_outbox_event_attempts();

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'job.outbox_events'::regclass
          and conname = 'outbox_events_status_chk'
    ) then
        alter table job.outbox_events
            add constraint outbox_events_status_chk
            check (status in ('pending', 'processing', 'done', 'failed')) not valid;
    end if;

    begin
        alter table job.outbox_events validate constraint outbox_events_status_chk;
    exception
        when check_violation then
            raise notice 'outbox_events_status_chk remains not valid because existing rows violate the constraint';
    end;
end $$;

create unique index if not exists outbox_events_dedupe_uidx
    on job.outbox_events (tenant_id, dedupe_key)
    where dedupe_key is not null and status in ('pending', 'processing');

create index if not exists outbox_events_claim_idx
    on job.outbox_events (status, available_at, locked_at);

create table if not exists job.read_model_dirty_scopes (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_type text not null,
    scope_key text not null,
    month date,
    reason text,
    source_version bigint not null default 0,
    status text not null default 'pending',
    attempts integer not null default 0,
    locked_by text,
    locked_at timestamptz,
    next_run_at timestamptz not null default now(),
    last_error text,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (status in ('pending', 'processing', 'done', 'failed', 'superseded'))
);

create unique index if not exists read_model_dirty_scopes_active_uidx
    on job.read_model_dirty_scopes (tenant_id, scope_type, scope_key)
    where status in ('pending', 'processing');

create index if not exists read_model_dirty_scopes_claim_idx
    on job.read_model_dirty_scopes (status, next_run_at, locked_at);

create index if not exists read_model_dirty_scopes_scope_idx
    on job.read_model_dirty_scopes (tenant_id, scope_type, scope_key, updated_at desc);

create table if not exists job.runtime_worker_heartbeats (
    id uuid primary key default gen_random_uuid(),
    worker_id text not null,
    worker_kind text not null,
    status text not null,
    last_seen_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists runtime_worker_heartbeats_worker_uidx
    on job.runtime_worker_heartbeats (worker_id);

alter table app.file_objects
    add column if not exists etag text,
    add column if not exists migration_status text;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant usage on schema job to fin_ops_api;
        grant select, insert, update on job.outbox_events to fin_ops_api;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_api;
        grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_api;
        grant usage, select on all sequences in schema job to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant usage on schema job to fin_ops_worker;
        grant select, insert, update on job.outbox_events to fin_ops_worker;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_worker;
        grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_worker;
        grant usage, select on all sequences in schema job to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant usage on schema job to fin_ops_readonly;
        grant select on job.outbox_events to fin_ops_readonly;
        grant select on job.read_model_dirty_scopes to fin_ops_readonly;
        grant select on job.runtime_worker_heartbeats to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant usage, create on schema job to fin_ops_migrator;
        grant select, insert, update on job.outbox_events to fin_ops_migrator;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_migrator;
        grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_migrator;
        grant usage, select on all sequences in schema job to fin_ops_migrator;
    end if;
end $$;
