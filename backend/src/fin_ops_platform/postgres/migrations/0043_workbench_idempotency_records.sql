create table if not exists app.workbench_idempotency_records (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    actor_id text not null,
    action_name text not null,
    idempotency_key text not null,
    request_fingerprint text not null,
    status text not null default 'reserved',
    request_payload jsonb not null default '{}'::jsonb,
    response_payload jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    outbox_event_ids jsonb not null default '[]'::jsonb,
    trace_id text,
    reserved_at timestamptz not null default now(),
    completed_at timestamptz,
    expires_at timestamptz,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint workbench_idempotency_status_chk
        check (status in ('reserved', 'committed', 'failed')),
    constraint workbench_idempotency_fingerprint_chk
        check (request_fingerprint ~ '^[0-9a-f]{64}$')
);

create unique index if not exists workbench_idempotency_identity_uidx
    on app.workbench_idempotency_records (tenant_id, actor_id, idempotency_key);

create index if not exists workbench_idempotency_action_status_idx
    on app.workbench_idempotency_records (tenant_id, action_name, status, created_at desc);

create index if not exists workbench_idempotency_expires_idx
    on app.workbench_idempotency_records (expires_at)
    where expires_at is not null;

create index if not exists workbench_idempotency_committed_idx
    on app.workbench_idempotency_records (tenant_id, actor_id, completed_at desc)
    where status = 'committed';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select, insert, update on app.workbench_idempotency_records to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select on app.workbench_idempotency_records to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.workbench_idempotency_records to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update on app.workbench_idempotency_records to fin_ops_migrator;
    end if;
end $$;
