create table if not exists read_model.turnover_ledger_scopes (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null unique,
    scope_month date,
    row_count integer not null default 0,
    source_versions jsonb not null default '{}'::jsonb,
    statistics jsonb not null default '{}'::jsonb,
    generation bigint not null default 0,
    published_source_version bigint,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (row_count >= 0),
    check (generation >= 0),
    check (published_source_version is null or published_source_version >= 0),
    check (cache_status in ('fresh', 'stale'))
);

create index if not exists turnover_ledger_scopes_month_idx
    on read_model.turnover_ledger_scopes (scope_month, generated_at desc);

-- Remove the short-lived row marker representation. Scope statistics now have
-- an explicit persistence boundary and never occupy a business row payload.
update read_model.turnover_ledger_rows
set raw_payload = raw_payload - 'page_statistics',
    updated_at = now()
where raw_payload ? 'page_statistics';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.turnover_ledger_scopes to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.turnover_ledger_scopes to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.turnover_ledger_scopes to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.turnover_ledger_scopes to fin_ops_migrator;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.turnover_ledger_scopes to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant select, insert, update, delete on read_model.turnover_ledger_scopes to fin_ops_app;
    end if;
end $$;
