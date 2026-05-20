create table if not exists app.pending_invoice_manual_invoice_commands (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    command_id text not null unique,
    request_id text,
    request_key text,
    status text not null,
    invoice_id text,
    relation_case_id text,
    actor_id text,
    error_code text,
    error_message text,
    last_successful_status text,
    attempt_count integer not null default 0,
    status_history text[] not null default array[]::text[],
    result_payload jsonb not null default '{}'::jsonb,
    command_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists pending_invoice_commands_request_key_idx
    on app.pending_invoice_manual_invoice_commands (request_key);

create index if not exists pending_invoice_commands_status_idx
    on app.pending_invoice_manual_invoice_commands (status, updated_at desc);

create index if not exists pending_invoice_commands_invoice_idx
    on app.pending_invoice_manual_invoice_commands (invoice_id)
    where invoice_id is not null;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select, insert, update, delete on app.pending_invoice_manual_invoice_commands to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on app.pending_invoice_manual_invoice_commands to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.pending_invoice_manual_invoice_commands to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.pending_invoice_manual_invoice_commands to fin_ops_migrator;
    end if;
end $$;
