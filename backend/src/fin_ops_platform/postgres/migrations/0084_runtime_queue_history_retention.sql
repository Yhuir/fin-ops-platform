-- Runtime queue history retention support.
--
-- The retention job deletes only terminal status='done' history through a
-- root-owned migrator env. API and worker roles keep their existing
-- select/insert/update boundary and do not receive delete permission.

create index if not exists outbox_events_done_retention_idx
    on job.outbox_events (
        (coalesce(processed_at, updated_at, created_at)),
        event_type,
        id
    )
    where status = 'done';

create index if not exists read_model_dirty_scopes_done_retention_idx
    on job.read_model_dirty_scopes (
        (coalesce(updated_at, created_at)),
        scope_type,
        id
    )
    where status = 'done';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant delete on job.outbox_events to fin_ops_migrator;
        grant delete on job.read_model_dirty_scopes to fin_ops_migrator;
    end if;
end $$;
