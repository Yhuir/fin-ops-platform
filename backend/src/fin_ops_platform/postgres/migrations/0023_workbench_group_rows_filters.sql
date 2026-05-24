create table if not exists read_model.workbench_group_rows (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null,
    scope_month date,
    zone text not null,
    group_id text not null,
    pane text not null,
    row_id text not null,
    row_role text not null default 'normal',
    row_index integer not null default 0,
    source_kind text not null,
    status text not null,
    time_value text,
    time_date date,
    column_values jsonb not null default '{}'::jsonb,
    searchable_text text not null default '',
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists workbench_group_rows_scope_zone_group_pane_role_row_uidx
    on read_model.workbench_group_rows (scope_key, zone, group_id, pane, row_role, row_id);

create index if not exists workbench_group_rows_scope_zone_group_idx
    on read_model.workbench_group_rows (scope_key, zone, group_id, pane, row_index);

create index if not exists workbench_group_rows_scope_zone_pane_time_idx
    on read_model.workbench_group_rows (scope_key, zone, pane, time_date, group_id)
    where time_date is not null;

create index if not exists workbench_group_rows_scope_zone_pane_source_idx
    on read_model.workbench_group_rows (scope_key, zone, pane, source_kind, group_id);

create index if not exists workbench_group_rows_column_values_gin
    on read_model.workbench_group_rows using gin (column_values);

create index if not exists workbench_group_rows_searchable_text_trgm
    on read_model.workbench_group_rows using gin (searchable_text gin_trgm_ops);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_group_rows to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_group_rows to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_group_rows to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_group_rows to fin_ops_migrator;
    end if;
end $$;
