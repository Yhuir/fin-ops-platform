create table if not exists app.oa_pending_payment_admissions (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_key text not null,
    oa_id text not null,
    workflow_status text,
    applicant text,
    project_name text,
    project_name_display text,
    amount numeric(20, 6),
    source_signature text not null,
    source_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    registered_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, scope_key, oa_id)
);

create index if not exists oa_pending_payment_admissions_oa_idx
    on app.oa_pending_payment_admissions (tenant_id, oa_id, scope_key);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select on app.oa_pending_payment_admissions to fin_ops_app_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on app.oa_pending_payment_admissions to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on app.oa_pending_payment_admissions to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.oa_pending_payment_admissions to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.oa_pending_payment_admissions to fin_ops_migrator;
    end if;
end $$;
