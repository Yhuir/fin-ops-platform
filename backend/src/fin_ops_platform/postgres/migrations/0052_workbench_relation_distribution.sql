create table if not exists read_model.workbench_relation_scopes (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_key text not null,
    scope_month date,
    row_count integer not null default 0,
    group_count integer not null default 0,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    source_versions jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, scope_key)
);

create table if not exists read_model.workbench_relation_groups (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    group_id text not null,
    scope_key text not null,
    scope_month date not null,
    relation_source text not null,
    relation_kind text not null,
    relation_status text not null default 'linked',
    oa_row_ids text[] not null default array[]::text[],
    bank_transaction_ids text[] not null default array[]::text[],
    input_invoice_ids text[] not null default array[]::text[],
    output_invoice_ids text[] not null default array[]::text[],
    source_versions jsonb not null default '{}'::jsonb,
    payload jsonb not null,
    raw_payload jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, scope_key, group_id)
);

create table if not exists read_model.workbench_relation_rows (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    row_id text not null,
    row_type text not null,
    scope_key text not null,
    scope_month date not null,
    relation_status text not null,
    group_ids text[] not null default array[]::text[],
    linked_oa jsonb not null default '[]'::jsonb,
    linked_bank_transactions jsonb not null default '[]'::jsonb,
    linked_input_invoices jsonb not null default '[]'::jsonb,
    linked_output_invoices jsonb not null default '[]'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    payload jsonb not null,
    raw_payload jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, row_id)
);

create index if not exists workbench_relation_scopes_tenant_scope_idx
    on read_model.workbench_relation_scopes (tenant_id, scope_key);
create index if not exists workbench_relation_groups_scope_idx
    on read_model.workbench_relation_groups (tenant_id, scope_key, relation_kind);
create index if not exists workbench_relation_groups_scope_group_idx
    on read_model.workbench_relation_groups (tenant_id, scope_key, group_id);
create index if not exists workbench_relation_groups_bank_gin
    on read_model.workbench_relation_groups using gin (bank_transaction_ids);
create index if not exists workbench_relation_groups_oa_gin
    on read_model.workbench_relation_groups using gin (oa_row_ids);
create index if not exists workbench_relation_groups_input_invoice_gin
    on read_model.workbench_relation_groups using gin (input_invoice_ids);
create index if not exists workbench_relation_groups_output_invoice_gin
    on read_model.workbench_relation_groups using gin (output_invoice_ids);
create index if not exists workbench_relation_rows_scope_type_status_idx
    on read_model.workbench_relation_rows (tenant_id, scope_key, row_type, relation_status);
create index if not exists workbench_relation_rows_month_type_status_idx
    on read_model.workbench_relation_rows (tenant_id, scope_month, row_type, relation_status);
create index if not exists workbench_relation_rows_group_ids_gin
    on read_model.workbench_relation_rows using gin (group_ids);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.workbench_relation_scopes to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.workbench_relation_groups to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.workbench_relation_rows to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_relation_scopes to fin_ops_api;
        grant select on read_model.workbench_relation_groups to fin_ops_api;
        grant select on read_model.workbench_relation_rows to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_relation_scopes to fin_ops_worker;
        grant select, insert, update, delete on read_model.workbench_relation_groups to fin_ops_worker;
        grant select, insert, update, delete on read_model.workbench_relation_rows to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_relation_scopes to fin_ops_readonly;
        grant select on read_model.workbench_relation_groups to fin_ops_readonly;
        grant select on read_model.workbench_relation_rows to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_relation_scopes to fin_ops_migrator;
        grant select, insert, update, delete on read_model.workbench_relation_groups to fin_ops_migrator;
        grant select, insert, update, delete on read_model.workbench_relation_rows to fin_ops_migrator;
    end if;
end $$;
