alter table job.outbox_events
    add column if not exists schema_version integer not null default 1,
    add column if not exists source_version bigint,
    add column if not exists priority text not null default 'normal',
    add column if not exists trace_id text,
    add column if not exists max_attempts integer not null default 5,
    add column if not exists dead_lettered_at timestamptz;

update job.outbox_events
set source_version = (payload->>'source_version')::bigint
where source_version is null
  and payload ? 'source_version'
  and payload->>'source_version' ~ '^[0-9]+$';

alter table job.read_model_dirty_scopes
    add column if not exists priority text not null default 'normal',
    add column if not exists trace_id text;

do $$
begin
    alter table job.outbox_events drop constraint if exists outbox_events_status_chk;
    alter table job.outbox_events
        add constraint outbox_events_status_chk
        check (status in ('pending', 'processing', 'done', 'failed', 'dead_lettered')) not valid;

    begin
        alter table job.outbox_events validate constraint outbox_events_status_chk;
    exception
        when check_violation then
            raise notice 'outbox_events_status_chk remains not valid because existing rows violate the constraint';
    end;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'job.outbox_events'::regclass
          and conname = 'outbox_events_priority_chk'
    ) then
        alter table job.outbox_events
            add constraint outbox_events_priority_chk
            check (priority in ('low', 'normal', 'high', 'urgent')) not valid;
    end if;

    begin
        alter table job.outbox_events validate constraint outbox_events_priority_chk;
    exception
        when check_violation then
            raise notice 'outbox_events_priority_chk remains not valid because existing rows violate the constraint';
    end;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'job.outbox_events'::regclass
          and conname = 'outbox_events_schema_version_chk'
    ) then
        alter table job.outbox_events
            add constraint outbox_events_schema_version_chk
            check (schema_version = 1) not valid;
    end if;

    begin
        alter table job.outbox_events validate constraint outbox_events_schema_version_chk;
    exception
        when check_violation then
            raise notice 'outbox_events_schema_version_chk remains not valid because existing rows violate the constraint';
    end;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'job.outbox_events'::regclass
          and conname = 'outbox_events_max_attempts_chk'
    ) then
        alter table job.outbox_events
            add constraint outbox_events_max_attempts_chk
            check (max_attempts > 0) not valid;
    end if;

    begin
        alter table job.outbox_events validate constraint outbox_events_max_attempts_chk;
    exception
        when check_violation then
            raise notice 'outbox_events_max_attempts_chk remains not valid because existing rows violate the constraint';
    end;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'job.read_model_dirty_scopes'::regclass
          and conname = 'read_model_dirty_scopes_priority_chk'
    ) then
        alter table job.read_model_dirty_scopes
            add constraint read_model_dirty_scopes_priority_chk
            check (priority in ('low', 'normal', 'high', 'urgent')) not valid;
    end if;

    begin
        alter table job.read_model_dirty_scopes validate constraint read_model_dirty_scopes_priority_chk;
    exception
        when check_violation then
            raise notice 'read_model_dirty_scopes_priority_chk remains not valid because existing rows violate the constraint';
    end;
end $$;

drop index if exists job.outbox_events_dedupe_uidx;

create unique index if not exists outbox_events_dedupe_uidx
    on job.outbox_events (tenant_id, dedupe_key)
    where dedupe_key is not null and status = 'pending';

create index if not exists outbox_events_claim_priority_idx
    on job.outbox_events (status, priority, available_at, created_at, id)
    where status in ('pending', 'processing');

create index if not exists outbox_events_trace_idx
    on job.outbox_events (trace_id)
    where trace_id is not null;

create or replace view job.runtime_outbox_envelope_v1 as
select
    id::text as event_id,
    tenant_id,
    event_type,
    aggregate_type,
    aggregate_id,
    scope_type,
    scope_key,
    source_version,
    priority,
    status,
    attempt_count,
    attempts,
    last_error,
    available_at,
    locked_by,
    locked_at,
    trace_id,
    schema_version,
    dedupe_key,
    payload,
    raw_payload,
    created_at,
    updated_at,
    processed_at,
    dead_lettered_at
from job.outbox_events;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on job.runtime_outbox_envelope_v1 to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select on job.runtime_outbox_envelope_v1 to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on job.runtime_outbox_envelope_v1 to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select on job.runtime_outbox_envelope_v1 to fin_ops_migrator;
    end if;
end $$;
