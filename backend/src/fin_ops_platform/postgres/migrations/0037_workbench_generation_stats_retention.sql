create table if not exists read_model.workbench_generation_stats (
    id uuid primary key default gen_random_uuid(),
    generation_id text not null,
    scope_key text not null,
    zone text not null,
    status_bucket text not null default 'all',
    total_groups integer not null default 0,
    oa_count integer not null default 0,
    bank_count integer not null default 0,
    invoice_count integer not null default 0,
    row_count_total integer not null default 0,
    computed_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists workbench_generation_stats_scope_zone_status_uidx
    on read_model.workbench_generation_stats (generation_id, scope_key, zone, status_bucket);

create index if not exists workbench_generation_stats_scope_zone_idx
    on read_model.workbench_generation_stats (scope_key, zone, computed_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_generation_stats to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_generation_stats to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_generation_stats to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_generation_stats to fin_ops_migrator;
    end if;
end $$;
