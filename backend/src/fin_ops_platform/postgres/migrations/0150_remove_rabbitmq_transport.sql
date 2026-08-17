set local lock_timeout = '5s';
set local statement_timeout = '2min';

-- RabbitMQ was only a secondary transport over the PostgreSQL durable outbox.
-- The application now claims job.outbox_events directly, so remove the stale
-- publish lifecycle without changing the durable queue or its audit history.
drop view if exists job.runtime_outbox_envelope_v1;

drop index if exists job.outbox_events_publish_claim_idx;
drop index if exists job.outbox_events_publish_lock_idx;
drop index if exists job.outbox_events_rabbitmq_message_idx;
drop index if exists job.outbox_events_operation_barrier_latest_scope_idx;

alter table job.outbox_events
    drop constraint if exists outbox_events_publish_status_chk,
    drop constraint if exists outbox_events_publish_attempt_count_nonnegative_chk,
    drop constraint if exists outbox_events_publish_lock_pair_chk,
    drop constraint if exists outbox_events_publishing_lock_required_chk,
    drop constraint if exists outbox_events_published_timestamps_chk;

alter table job.outbox_events
    drop column if exists publish_status,
    drop column if exists published_at,
    drop column if exists publish_attempt_count,
    drop column if exists publish_last_error,
    drop column if exists next_publish_at,
    drop column if exists publish_locked_by,
    drop column if exists publish_locked_at,
    drop column if exists rabbitmq_exchange,
    drop column if exists rabbitmq_routing_key,
    drop column if exists rabbitmq_message_id,
    drop column if exists publish_confirmed_at;

create index if not exists outbox_events_operation_barrier_latest_scope_idx
    on job.outbox_events (
        tenant_id,
        event_type,
        (coalesce(scope_type, raw_payload->>'scope_type', payload->>'scope_type', aggregate_type, '')),
        (coalesce(scope_key, raw_payload->>'scope_key', payload->>'scope_key', aggregate_id, '')),
        created_at desc,
        id desc
    )
    include (status, updated_at, last_error)
    where status in ('pending', 'processing', 'failed', 'dead_lettered', 'done');

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
