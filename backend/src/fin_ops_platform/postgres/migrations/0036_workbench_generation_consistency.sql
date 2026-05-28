alter table read_model.workbench_generations
    add column if not exists build_batch_id text;

alter table read_model.workbench_generations
    add column if not exists parent_generation_ids jsonb not null default '[]'::jsonb;

alter table read_model.workbench_generations
    add column if not exists error_reason text;

alter table read_model.workbench_generations
    add column if not exists validated_at timestamptz;

alter table read_model.workbench_generations
    add column if not exists consistency_status text not null default 'unchecked';

do $$
begin
    alter table read_model.workbench_generations
        add constraint workbench_generations_consistency_status_check
        check (consistency_status in ('unchecked', 'validating', 'consistent', 'inconsistent'));
exception
    when duplicate_object then null;
end $$;

create or replace view read_model.workbench_generation_consistency as
with row_counts as (
    select generation_id, scope_key, count(distinct row_id)::bigint as actual_row_count
    from read_model.workbench_rows
    group by generation_id, scope_key
),
group_counts as (
    select generation_id, scope_key, count(*)::bigint as actual_group_count
    from read_model.workbench_groups
    group by generation_id, scope_key
),
group_row_counts as (
    select
        generation_id,
        scope_key,
        count(distinct row_id) filter (where coalesce(row_role, '') <> 'summary')::bigint as actual_group_row_count
    from read_model.workbench_group_rows
    group by generation_id, scope_key
),
summary_counts as (
    select generation_id, scope_key, count(*)::bigint as actual_summary_count
    from read_model.workbench_summary
    group by generation_id, scope_key
)
select
    gen.tenant_id,
    gen.scope_key,
    gen.generation_id,
    gen.status,
    gen.row_count as metadata_row_count,
    gen.group_count as metadata_group_count,
    gen.summary_count as metadata_summary_count,
    coalesce(row_counts.actual_row_count, 0)::bigint as actual_row_count,
    coalesce(group_counts.actual_group_count, 0)::bigint as actual_group_count,
    coalesce(group_row_counts.actual_group_row_count, 0)::bigint as actual_group_row_count,
    coalesce(summary_counts.actual_summary_count, 0)::bigint as actual_summary_count,
    case
        when gen.status <> 'active' then 'inactive'
        when coalesce(gen.build_metadata->>'tombstone', 'false') = 'true'
             and gen.row_count = 0
             and gen.group_count = 0
             then 'consistent'
        when gen.group_count <> coalesce(group_counts.actual_group_count, 0) then 'inconsistent'
        when gen.row_count > 0 and coalesce(group_row_counts.actual_group_row_count, 0) = 0 then 'inconsistent'
        when gen.summary_count > 0 and coalesce(summary_counts.actual_summary_count, 0) = 0 then 'inconsistent'
        else 'consistent'
    end as consistency_status,
    gen.parent_generation_ids,
    gen.build_batch_id,
    gen.build_metadata,
    gen.last_error,
    gen.error_reason,
    gen.activated_at,
    gen.updated_at
from read_model.workbench_generations gen
left join row_counts
  on row_counts.generation_id = gen.generation_id
 and row_counts.scope_key = gen.scope_key
left join group_counts
  on group_counts.generation_id = gen.generation_id
 and group_counts.scope_key = gen.scope_key
left join group_row_counts
  on group_row_counts.generation_id = gen.generation_id
 and group_row_counts.scope_key = gen.scope_key
left join summary_counts
  on summary_counts.generation_id = gen.generation_id
 and summary_counts.scope_key = gen.scope_key;

create index if not exists workbench_generations_build_batch_idx
    on read_model.workbench_generations (tenant_id, build_batch_id)
    where build_batch_id is not null;

create index if not exists workbench_generations_consistency_status_idx
    on read_model.workbench_generations (tenant_id, consistency_status, updated_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_generation_consistency to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select on read_model.workbench_generation_consistency to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_generation_consistency to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select on read_model.workbench_generation_consistency to fin_ops_migrator;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select on read_model.workbench_generation_consistency to fin_ops_app_runtime;
        grant update (
            build_batch_id,
            parent_generation_ids,
            error_reason,
            validated_at,
            consistency_status,
            updated_at
        ) on read_model.workbench_generations to fin_ops_app_runtime;
    end if;
end $$;
