set local lock_timeout = '5s';
set local statement_timeout = '2min';

-- `attempts` is the durable queue retry counter. `attempt_count` remains only
-- as a compatibility mirror for legacy readers.
create or replace function job.sync_outbox_event_attempts()
returns trigger
language plpgsql
as $$
begin
    new.attempt_count := new.attempts;
    return new;
end;
$$;

drop trigger if exists outbox_events_sync_attempts_trg on job.outbox_events;

create trigger outbox_events_sync_attempts_trg
    before insert or update of attempts, attempt_count on job.outbox_events
    for each row
    execute function job.sync_outbox_event_attempts();

update job.outbox_events
set attempt_count = attempts
where attempt_count is distinct from attempts;

-- These constraints protect all new and changed envelopes immediately without
-- forcing a production-table validation scan during this release.
alter table job.outbox_events
    add constraint outbox_events_attempts_nonnegative_chk
        check (attempts >= 0) not valid,
    add constraint outbox_events_attempt_count_mirror_chk
        check (attempt_count = attempts) not valid,
    add constraint outbox_events_publish_attempt_count_nonnegative_chk
        check (publish_attempt_count >= 0) not valid,
    add constraint outbox_events_event_type_nonempty_chk
        check (btrim(event_type) <> '') not valid,
    add constraint outbox_events_tenant_id_nonempty_chk
        check (btrim(tenant_id) <> '') not valid,
    add constraint outbox_events_payload_object_chk
        check (jsonb_typeof(payload) = 'object') not valid,
    add constraint outbox_events_raw_payload_object_chk
        check (jsonb_typeof(raw_payload) = 'object') not valid,
    add constraint outbox_events_runtime_lock_pair_chk
        check ((locked_by is null) = (locked_at is null)) not valid,
    add constraint outbox_events_processing_lock_required_chk
        check (status <> 'processing' or (locked_by is not null and locked_at is not null)) not valid,
    add constraint outbox_events_publish_lock_pair_chk
        check ((publish_locked_by is null) = (publish_locked_at is null)) not valid,
    add constraint outbox_events_publishing_lock_required_chk
        check (
            publish_status <> 'publishing'
            or (publish_locked_by is not null and publish_locked_at is not null)
        ) not valid,
    add constraint outbox_events_terminal_processed_at_chk
        check (
            status not in ('done', 'failed', 'dead_lettered')
            or processed_at is not null
        ) not valid,
    add constraint outbox_events_dead_letter_timestamp_chk
        check (status <> 'dead_lettered' or dead_lettered_at is not null) not valid,
    add constraint outbox_events_published_timestamps_chk
        check (
            publish_status <> 'published'
            or (published_at is not null and publish_confirmed_at is not null)
        ) not valid;
