create table if not exists app.oa_pending_payment_status_snapshots (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    flow_id text not null,
    pay_status integer not null,
    scope_month date,
    source_signature text not null,
    synced_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    unique (tenant_id, flow_id)
);

create index if not exists oa_pending_payment_status_snapshots_scope_idx
    on app.oa_pending_payment_status_snapshots (tenant_id, scope_month, flow_id);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.oa_pending_payment_status_snapshots to fin_ops_app_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on app.oa_pending_payment_status_snapshots to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on app.oa_pending_payment_status_snapshots to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.oa_pending_payment_status_snapshots to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.oa_pending_payment_status_snapshots to fin_ops_migrator;
    end if;
end $$;
