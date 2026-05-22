do $$
begin
    if exists (
        select 1
        from pg_available_extensions
        where name = 'pg_stat_statements'
    ) then
        begin
            create extension if not exists pg_stat_statements;
        exception
            when insufficient_privilege then
                raise notice 'Skipping pg_stat_statements extension creation because current role lacks privilege.';
        end;
    end if;
end $$;

create table if not exists read_model.workbench_summary (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null,
    scope_month date,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    summary jsonb not null default '{}'::jsonb,
    invoice_inventory jsonb not null default '{}'::jsonb,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists workbench_summary_scope_key_uidx
    on read_model.workbench_summary (scope_key);

create index if not exists workbench_summary_scope_month_idx
    on read_model.workbench_summary (scope_month, updated_at desc);

create index if not exists workbench_summary_source_version_idx
    on read_model.workbench_summary (((source_versions->>'source_version')::bigint))
    where source_versions ? 'source_version'
      and source_versions->>'source_version' ~ '^[0-9]+$';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_summary to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_summary to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_summary to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_summary to fin_ops_migrator;
    end if;
end $$;
