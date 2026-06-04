create table if not exists read_model.invoice_lifecycle_scopes (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_key text not null,
    scope_month date,
    row_count integer not null default 0,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    source_versions jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, scope_key)
);

create table if not exists read_model.invoice_lifecycle_rows (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    subject_id text not null,
    subject_type text not null,
    scope_key text not null,
    scope_month date not null,
    invoice_identity_key text,
    lifecycle_status text not null default 'unknown',
    acquisition_status jsonb not null default '{}'::jsonb,
    payment_status jsonb not null default '{}'::jsonb,
    collection_status jsonb not null default '{}'::jsonb,
    certification_status jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    payload jsonb not null,
    raw_payload jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, subject_type, subject_id)
);

create index if not exists invoice_lifecycle_scopes_tenant_scope_idx
    on read_model.invoice_lifecycle_scopes (tenant_id, scope_key);
create index if not exists invoice_lifecycle_rows_scope_type_idx
    on read_model.invoice_lifecycle_rows (tenant_id, scope_key, subject_type);
create index if not exists invoice_lifecycle_rows_month_type_status_idx
    on read_model.invoice_lifecycle_rows (tenant_id, scope_month, subject_type, lifecycle_status);
create index if not exists invoice_lifecycle_rows_subject_idx
    on read_model.invoice_lifecycle_rows (tenant_id, subject_id);
create index if not exists invoice_lifecycle_rows_identity_idx
    on read_model.invoice_lifecycle_rows (tenant_id, invoice_identity_key)
    where invoice_identity_key is not null;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.invoice_lifecycle_scopes to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.invoice_lifecycle_rows to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.invoice_lifecycle_scopes to fin_ops_api;
        grant select on read_model.invoice_lifecycle_rows to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.invoice_lifecycle_scopes to fin_ops_worker;
        grant select, insert, update, delete on read_model.invoice_lifecycle_rows to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.invoice_lifecycle_scopes to fin_ops_readonly;
        grant select on read_model.invoice_lifecycle_rows to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.invoice_lifecycle_scopes to fin_ops_migrator;
        grant select, insert, update, delete on read_model.invoice_lifecycle_rows to fin_ops_migrator;
    end if;
end $$;
