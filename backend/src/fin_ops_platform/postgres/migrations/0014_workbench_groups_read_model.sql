create table if not exists read_model.workbench_groups (
    id uuid primary key default gen_random_uuid(),
    group_id text not null,
    scope_key text not null,
    scope_month date,
    zone text not null,
    status text not null,
    group_type text not null,
    source_kinds text[] not null default array[]::text[],
    row_count integer not null default 0,
    searchable_text text not null default '',
    oa_sort_min text,
    oa_sort_max text,
    bank_sort_min text,
    bank_sort_max text,
    invoice_sort_min text,
    invoice_sort_max text,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table read_model.workbench_groups
    add column if not exists oa_sort_min text,
    add column if not exists oa_sort_max text,
    add column if not exists bank_sort_min text,
    add column if not exists bank_sort_max text,
    add column if not exists invoice_sort_min text,
    add column if not exists invoice_sort_max text;

create unique index if not exists workbench_groups_scope_zone_group_uidx
    on read_model.workbench_groups (scope_key, zone, group_id);

create index if not exists workbench_groups_scope_zone_idx
    on read_model.workbench_groups (scope_key, zone, updated_at desc);

create index if not exists workbench_groups_scope_month_zone_idx
    on read_model.workbench_groups (scope_month, zone, updated_at desc);

create index if not exists workbench_groups_source_kinds_gin
    on read_model.workbench_groups using gin (source_kinds);

create index if not exists workbench_groups_searchable_text_trgm
    on read_model.workbench_groups using gin (searchable_text gin_trgm_ops);

create index if not exists workbench_groups_oa_sort_idx
    on read_model.workbench_groups (scope_key, zone, oa_sort_min, oa_sort_max, updated_at desc);

create index if not exists workbench_groups_bank_sort_idx
    on read_model.workbench_groups (scope_key, zone, bank_sort_min, bank_sort_max, updated_at desc);

create index if not exists workbench_groups_invoice_sort_idx
    on read_model.workbench_groups (scope_key, zone, invoice_sort_min, invoice_sort_max, updated_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_groups to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_groups to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_groups to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_groups to fin_ops_migrator;
    end if;
end $$;
