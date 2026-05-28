create table if not exists read_model.workbench_generations (
    id uuid primary key default gen_random_uuid(),
    generation_id text not null unique,
    tenant_id text not null default 'default',
    scope_key text not null,
    status text not null,
    source_versions jsonb not null default '{}'::jsonb,
    schema_version text not null default 'workbench.generation.v1',
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    activated_at timestamptz,
    superseded_at timestamptz,
    row_count integer not null default 0,
    group_count integer not null default 0,
    summary_count integer not null default 0,
    checksum text,
    last_error text,
    build_metadata jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint workbench_generations_status_check
        check (status in ('building', 'active', 'failed', 'superseded'))
);

alter table read_model.workbench_snapshots
    add column if not exists generation_id text;

alter table read_model.workbench_summary
    add column if not exists generation_id text;

alter table read_model.workbench_rows
    add column if not exists generation_id text;

alter table read_model.workbench_groups
    add column if not exists generation_id text;

alter table read_model.workbench_group_rows
    add column if not exists generation_id text;

update read_model.workbench_snapshots
set generation_id = 'legacy:' || scope_key
where generation_id is null;

update read_model.workbench_summary
set generation_id = 'legacy:' || scope_key
where generation_id is null;

update read_model.workbench_rows
set generation_id = 'legacy:' || scope_key
where generation_id is null;

update read_model.workbench_groups
set generation_id = 'legacy:' || scope_key
where generation_id is null;

update read_model.workbench_group_rows
set generation_id = 'legacy:' || scope_key
where generation_id is null;

insert into read_model.workbench_generations(
    generation_id,
    tenant_id,
    scope_key,
    status,
    source_versions,
    started_at,
    completed_at,
    activated_at,
    row_count,
    group_count,
    summary_count,
    build_metadata,
    raw_payload
)
select
    'legacy:' || scopes.scope_key,
    'default',
    scopes.scope_key,
    'active',
    coalesce(snapshot_versions.source_versions, '{}'::jsonb),
    now(),
    now(),
    now(),
    coalesce(row_counts.row_count, 0),
    coalesce(group_counts.group_count, 0),
    case when summary_counts.summary_count > 0 then 1 else 0 end,
    jsonb_build_object('backfilled_by', '0034_workbench_generation_convergence'),
    jsonb_build_object('source', 'legacy_backfill', 'scope_key', scopes.scope_key)
from (
    select scope_key from read_model.workbench_snapshots
    union
    select scope_key from read_model.workbench_summary
    union
    select scope_key from read_model.workbench_rows
    union
    select scope_key from read_model.workbench_groups
    union
    select scope_key from read_model.workbench_group_rows
) scopes
left join (
    select scope_key, source_versions
    from read_model.workbench_snapshots
) snapshot_versions on snapshot_versions.scope_key = scopes.scope_key
left join (
    select scope_key, count(*)::integer as row_count
    from read_model.workbench_rows
    group by scope_key
) row_counts on row_counts.scope_key = scopes.scope_key
left join (
    select scope_key, count(*)::integer as group_count
    from read_model.workbench_groups
    group by scope_key
) group_counts on group_counts.scope_key = scopes.scope_key
left join (
    select scope_key, count(*)::integer as summary_count
    from read_model.workbench_summary
    group by scope_key
) summary_counts on summary_counts.scope_key = scopes.scope_key
where scopes.scope_key is not null
on conflict (generation_id) do nothing;

alter table read_model.workbench_snapshots
    alter column generation_id set not null;

alter table read_model.workbench_summary
    alter column generation_id set not null;

alter table read_model.workbench_rows
    alter column generation_id set not null;

alter table read_model.workbench_groups
    alter column generation_id set not null;

alter table read_model.workbench_group_rows
    alter column generation_id set not null;

alter table read_model.workbench_snapshots
    drop constraint if exists workbench_snapshots_scope_key_key;

drop index if exists read_model.workbench_summary_scope_key_uidx;
drop index if exists read_model.workbench_rows_scope_row_key;
drop index if exists read_model.workbench_groups_scope_zone_group_uidx;
drop index if exists read_model.workbench_group_rows_scope_zone_group_pane_role_row_uidx;

create unique index if not exists workbench_generations_active_scope_uidx
    on read_model.workbench_generations (tenant_id, scope_key)
    where status = 'active';

create index if not exists workbench_generations_scope_status_idx
    on read_model.workbench_generations (tenant_id, scope_key, status, updated_at desc);

create unique index if not exists workbench_snapshots_generation_scope_uidx
    on read_model.workbench_snapshots (generation_id, scope_key);

create unique index if not exists workbench_summary_generation_scope_uidx
    on read_model.workbench_summary (generation_id, scope_key);

create unique index if not exists workbench_rows_generation_scope_row_uidx
    on read_model.workbench_rows (generation_id, scope_key, row_id);

create unique index if not exists workbench_groups_generation_scope_zone_group_uidx
    on read_model.workbench_groups (generation_id, scope_key, zone, group_id);

create unique index if not exists workbench_group_rows_generation_scope_zone_group_pane_role_row_uidx
    on read_model.workbench_group_rows (generation_id, scope_key, zone, group_id, pane, row_role, row_id);

create index if not exists workbench_rows_generation_scope_status_idx
    on read_model.workbench_rows (generation_id, scope_key, status, updated_at desc);

create index if not exists workbench_groups_generation_scope_zone_sort_idx
    on read_model.workbench_groups (generation_id, scope_key, zone, updated_at desc);

create index if not exists workbench_group_rows_generation_scope_zone_group_idx
    on read_model.workbench_group_rows (generation_id, scope_key, zone, group_id, pane, row_index);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_generations to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_generations to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_generations to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_generations to fin_ops_migrator;
    end if;
end $$;
