alter table job.outbox_events
    add column if not exists publish_status text not null default 'unpublished',
    add column if not exists published_at timestamptz,
    add column if not exists publish_attempt_count integer not null default 0,
    add column if not exists publish_last_error text,
    add column if not exists next_publish_at timestamptz not null default now(),
    add column if not exists publish_locked_by text,
    add column if not exists publish_locked_at timestamptz,
    add column if not exists rabbitmq_exchange text,
    add column if not exists rabbitmq_routing_key text,
    add column if not exists rabbitmq_message_id text,
    add column if not exists publish_confirmed_at timestamptz;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'job.outbox_events'::regclass
          and conname = 'outbox_events_publish_status_chk'
    ) then
        alter table job.outbox_events
            add constraint outbox_events_publish_status_chk
            check (publish_status in ('unpublished', 'publishing', 'published', 'failed')) not valid;
    end if;

    begin
        alter table job.outbox_events validate constraint outbox_events_publish_status_chk;
    exception
        when check_violation then
            raise notice 'outbox_events_publish_status_chk remains not valid because existing rows violate the constraint';
    end;
end $$;

create index if not exists outbox_events_publish_claim_idx
    on job.outbox_events (publish_status, next_publish_at, available_at, status, priority, created_at, id)
    where publish_status in ('unpublished', 'failed');

create index if not exists outbox_events_publish_lock_idx
    on job.outbox_events (publish_status, publish_locked_at)
    where publish_status = 'publishing';

create index if not exists outbox_events_rabbitmq_message_idx
    on job.outbox_events (rabbitmq_message_id)
    where rabbitmq_message_id is not null;

drop view if exists job.runtime_outbox_envelope_v1;

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
    publish_status,
    published_at,
    publish_attempt_count,
    publish_last_error,
    next_publish_at,
    publish_locked_by,
    publish_locked_at,
    rabbitmq_exchange,
    rabbitmq_routing_key,
    rabbitmq_message_id,
    publish_confirmed_at,
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
